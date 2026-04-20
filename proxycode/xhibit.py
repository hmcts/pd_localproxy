#
# File: xhibit.py
#
# Author: Harjevaan Hayer
#
# Change History
#
# Date         Author            Reason
# 2016-04-09   Warren Ayling     Removed ScreenX and ScreenY against the CDU. Added Powersave Schedule against SITE.
# 2016-04-09   Warren Ayling     Added "VERSION" element to the CDU, being a fixed version associated with this script.
# 2016-04-10   Warren Ayling     Introducing a new command line argument to only return CDU data.
# 2016-04-15   Sean Bulley       Renamed the "COURT_ROOM" XML element, and always added powersave element with ENABLED/DISABLD value
#
CONST_VERSION = "1.0.2"

import pymysql
import sys
import re
import configparser
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import os.path
import logging
import platform		# used with syslog to determine the OS type to control which FACILITY to log against
if (platform.system() != "Windows"):
	import syslog
import json;
import datetime;
from operator import itemgetter;

pageIsEnglish = True

# reset error state to successful
error = False
errorMsg = ''
errorCode = ''

logging.basicConfig(filename='xhibit.log',level=logging.DEBUG, filemode="w")
logging.debug('Start logging')

#need to add http://localhost/xhibit/ to hardcode url where url is fetched

#command line format:
#   "python xhibit.py MACADDRESS PATHTOINIFILE <optional: CURRENTPAGEINDEX [number: 0 or more]> <optional: data_refresh [number: 1]>"
# returns the page type and Page XML detail from the XHIBIT content, which includes
# 1. Last Updated Date
# 2. Page Type
# 3. Current Page Index along with the current page url

# this method iterates over prioritised (using the "priority" dictionary) schedules
#  in sequence, returning "True" if the current date/time falls within time range
def iterateSchedules(schedules):
	# always assume no powersave
	powersave = False;

	orderedPowersaveSchedule = sorted(schedules, key=itemgetter('priority'));
	for thisPrioritySchedule in orderedPowersaveSchedule:
		logging.debug ("Value: " + thisPrioritySchedule["label"]);
		logging.debug ("Value: " + str(thisPrioritySchedule["priority"]));
		
		isToday = False;
		if "date" in thisPrioritySchedule:
			# join the array of dates in format (yyyy-mm-dd) to a single string
			dayValidator = ",".join(thisPrioritySchedule["date"]);
			
			# check to see if the current date (yyyy-mm-dd) is within the string
			todaysDate = datetime.date.today();
			if str(todaysDate) in dayValidator:
				logging.debug(str(todayDate) + " is in " + dayValidator);
				isToday = True;
		
		if "day" in thisPrioritySchedule:
			# join the array of days to a single string
			dayValidator = ",".join(thisPrioritySchedule["day"]).upper();
			
			# check to see if today is within the string
			todayIndexIs = datetime.date.today().weekday();
			weekdays = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"];
			todayIs = weekdays[todayIndexIs];
			logging.debug ("Today is: " + todayIs);
			
			if todayIs in dayValidator:
				logging.debug(todayIs + " is in " + dayValidator);
				isToday = True;

		if isToday:
			powersave = iterateTimeRange(thisPrioritySchedule["schedule"]);
		
		# stop if powersave has alreadya been identified
		if powersave:
			break;
	
	return powersave;

# this method iterates over an ordered list of time ranges (using "from")
def iterateTimeRange(timeRanges):
	# assume not within time range
	withinTime = False;
	
	# time format hh:mm
	pattern = re.compile("^[0-2][0-9]:[0-5][0-9]$");

	orderedTimeRanges = sorted(timeRanges, key=itemgetter('from'));
	for thisTimeRange in orderedTimeRanges:
		# validate the input
		if not (pattern.match(thisTimeRange["from"]) and pattern.match(thisTimeRange["to"])):
			logging.debug ("Invalid: From (" + thisTimeRange["from"] + "), to (" + thisTimeRange["to"] + ")");
			continue;
		
		myFrom = datetime.time(int(thisTimeRange["from"][0:2]), int(thisTimeRange["from"][3:5]));
		myTo = datetime.time(int(thisTimeRange["to"][0:2]), int(thisTimeRange["to"][3:5]));
		
		# To must be greater than from = else we have an error in input data
		if myTo >= myFrom:
			timeNow = datetime.datetime.now().time();
			
			if (timeNow >= myFrom) and(timeNow <= myTo):
				withinTime = True;
		
		# if found, no need to check anymore ranges
		if withinTime:
			logging.debug ("Within range: From (" + thisTimeRange["from"] + "), to (" + thisTimeRange["to"] + ")");
			break;
		else:
			logging.debug ("Not in range: From (" + thisTimeRange["from"] + "), to (" + thisTimeRange["to"] + ")");
	
	return withinTime;

def formatPageXML(soup, currentPageIndex, indexUrl):
	global pageIsEnglish 
	pageType = None
	pageXMLstr = "\n\t<PAGE>"
	logging.debug("formatPageXML") #logging.debug()
	try:
		logging.debug(soup.title)
		# extract Last Updated from the page
		myLastUpdated = soup.find('td', { "class" : "last-updated-date" })
		if myLastUpdated is not None:
			if ("Last" in myLastUpdated.get_text()):
				pageIsEnglish = True
				pageXMLstr = pageXMLstr + "\n\t\t<LANGUAGE>English</LANGUAGE>"
			else:
				pageIsEnglish = False
				pageXMLstr = pageXMLstr + "\n\t\t<LANGUAGE>Welsh</LANGUAGE>"

			if(pageIsEnglish):
				pageXMLstr = pageXMLstr + "\n\t\t<LAST-UPDATED>%s</LAST-UPDATED>" % myLastUpdated.get_text().split("Last updated: ")[1].strip()
			else:
				pageXMLstr = pageXMLstr + "\n\t\t<LAST-UPDATED>%s</LAST-UPDATED>" % myLastUpdated.get_text().split("Diweddarwyd Ddiwethaf: ")[1].strip()

		if (currentPageIndex is not None) and (currentPageIndex >= 0):
			pageXMLstr = pageXMLstr + "\n\t\t<CURRENT-PAGE-INDEX>%s</CURRENT-PAGE-INDEX>" % currentPageIndex
			pageXMLstr = pageXMLstr + "\n\t\t<CURRENT-URL>%s</CURRENT-URL>" % indexUrl
		# check for no information
		noInfoDiv = soup.find('div', { "class" : "no-information" })
		if noInfoDiv is not None:
			# then there is no info to display
			pageType = "No Info"
			logging.debug("No info")
		else:
			logging.debug("Info")
			# need to inspect various different HTML responses from the XHIBIT Public Display application
			# 1. Daily List => page title is "Public Display: Daily List"
			# 2. Court Room Detail => page title is "Public Display: Court <number> Detail"; it ends with "Detail"
			# 3. Court Room List => page title is "Public Display: Court 1 List"; it ends with "List" but it is not "Public Display: Daily List"
			# 4. Summary by Name -=> page title is "Public Display: Summary By Name"
			# 5. All Case Status -=> page title is "Public Display: All Case Status"
			# 6. Jury Current Status => page title is "Public Display: Jury Current Status"
			# 7. All Court Status => page title is "Public Dispaly: All Court Status"
			logging.debug("pageTitle: " + soup.title.get_text())
			
			pageTitle = soup.title.get_text()
			if pageTitle.endswith("All Case Status"):
				pageType = "All Case Status"
				logging.debug("Type: All case status")
			elif pageTitle.endswith("Summary By Name"):
				pageType = "Summary by Name"
				logging.debug("Type: summary by name")
			elif pageTitle != "Public Display: Daily List" and pageTitle.endswith("List"):
				pageType = "Court List"
				logging.debug("Type: Court list")
			elif pageTitle.endswith("Detail"):
				pageType = "Court Detail"
				logging.debug("Type: Court detail")
			elif pageTitle == "Public Display: Daily List":
				pageType = "Daily List"
				logging.debug("Type: Daily list")
			elif pageTitle.endswith("Jury Current Status"):
				pageType = "Jury Current Status"
			elif pageTitle.endswith("All Court Status"):
				pageType = "All Court Status"
			#added to handel Welsh content too
			elif pageTitle.endswith("Statws Pob Achos"):
				pageType = "All Case Status"
				logging.debug("Type: All case status")
			elif pageTitle.endswith("Crynodeb yn Ã´nw"):
				pageType = "Summary by Name"
				logging.debug("Type: summary by name")
			elif pageTitle != "Public Display: Rhestr Ddyddiol" and pageTitle.endswith("Rhestr"):
				pageType = "Court List"
				logging.debug("Type: Court list")
			elif pageTitle.endswith("Detail"):
				pageType = "Manylion"
				logging.debug("Type: Court detail")
			elif pageTitle == "Public Display: Rhestr Ddyddiol":
				pageType = "Daily List"
				logging.debug("Type: Daily list")
			elif pageTitle.endswith("Statws Gyfredol - Rheithgor"):
				pageType = "Jury Current Status"
			elif pageTitle.endswith("Statws Pob Llys"):
				pageType = "All Court Status"
			else:
				pageType = "No Info"
				logging.debug("Type: No info")

		pageXMLstr = pageXMLstr + "\n\t\t<TYPE>%s</TYPE>" % pageType
		pageXMLstr = pageXMLstr + "\n\t</PAGE>"

	except:
		# an error occurred extracting
		logging.error("Error")
		global error, errorMsg, errorCode
		error = True
		errorMsg = sys.exc_info()
		errorCode = 'PAGE_XML'
		logging.error(errorCode)
		logging.error(errorMsg)
		
		# reset the page XML
		pageXMLstr = None
		
		if displayError:
			logging.exception("XHIBIT page parsing")
	
	return pageType, pageXMLstr

def formatXML(cduXML, pageXML, contentsXML):
	logging.debug("formatXML")
	xmlStr = '<?xml version="1.0" encoding="ISO-8859-1"?>'
	#xmlStr = xmlStr + '\n<?xml-stylesheet type="text/xsl" href="example-xhibit.xsl"?>'
	xmlStr = xmlStr + "\n<COURT>"
	
	if cduXML:
		xmlStr = xmlStr + "\n%s" % cduXML
	
	if pageXML:
		xmlStr = xmlStr + "\n%s" % pageXML
		
	if contentsXML:
		xmlStr = xmlStr + "\n%s" % contentsXML

	xmlStr = xmlStr + "\n</COURT>"
	
	return xmlStr

def formatXhibitXML(soup, pageType):
	logging.debug("formatXhibitXML")
	xmlStr = ""
	
	try:
		if pageType == "All Case Status":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"

				myCourt = currentRow.find('td', { "class" : "court-room-name" })
				if myCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<ROOM>%s</ROOM>" % myCourt.get_text().strip()
				
				myCaseNumber = currentRow.find('td', { "class" : "case-number" })
				if myCaseNumber is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber.get_text().strip().replace('*', '')

				myHearingDescription = currentRow.find('td', { "class" : "hearing-description" })
				if myHearingDescription is not None:
					xmlStr = xmlStr + "\n\t\t\t<HEARINGDESCRIPTION>%s</HEARINGDESCRIPTION>" % myHearingDescription.get_text().strip()

				# hearing-progress can be replaced by live-status
				myHearingProgress = currentRow.find('td', { "class" : "hearing-progress" })
				myLiveStatus = currentRow.find('td', { "class" : "live-status" })
				if myHearingProgress is not None:
					xmlStr = xmlStr + "\n\t\t\t<HEARINGPROGRESS>%s</HEARINGPROGRESS>" % myHearingProgress.get_text().strip()
				if myLiveStatus is not None:
					xmlStr = xmlStr + "\n\t\t\t<LIVESTATUS>%s</LIVESTATUS>" % myLiveStatus.get_text().strip()

				myTime = currentRow.find('td', { "class" : "not-before-time" })
				if myTime is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOTBEFORE>%s</NOTBEFORE>" % myTime.get_text().strip()

				myDefendants = currentRow.findAll('div', {"class" : "defendant-name-restricted-size350"})
				xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
				for i,j in enumerate(myDefendants):
					xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
				xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"

				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"

		elif pageType == "Summary by Name":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"
				
				myDefendant = currentRow.find('td', { "class" : "defendant-name" })
				if myDefendant is not None:
					xmlStr = xmlStr + "\n\t\t\t<DEFENDANT>%s</DEFENDANT>" % myDefendant.get_text().strip()
				
				myCourt = currentRow.find('td', { "class" : "court-room-name" })
				if myCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<ROOM>%s</ROOM>" % myCourt.get_text().strip()
				
				myMovedCourt = currentRow.find('div', { "class" : "moved-highliht" })
				if myMovedCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<MOVEDROOM>%s</MOVEDROOM>" % myMovedCourt.get_text().strip()
				
				myTime = currentRow.find('td', { "class" : "not-before-time" })
				if myTime is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOTBEFORE>%s</NOTBEFORE>" % myTime.get_text().strip()
				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"

		elif pageType == "Court List":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"
				
				myHearingDescription = currentRow.find('td', { "class" : "hearing-description" })
				if myHearingDescription is not None:
					xmlStr = xmlStr + "\n\t\t\t<HEARINGDESCRIPTION>%s</HEARINGDESCRIPTION>" % myHearingDescription.get_text().strip()
				
				# hearing progress can be a TD class or a DIV class
				myHearingProgressTD = currentRow.find('td', { "class" : "hearing-progress" })
				if myHearingProgressTD is not None:
					xmlStr = xmlStr + "\n\t\t\t<HEARINGPROGRESS>%s</HEARINGPROGRESS>" % myHearingProgressTD.get_text().strip()
				myHearingProgressDIV = currentRow.find('div', { "class" : "hearing-progress" })
				if myHearingProgressDIV is not None:
					xmlStr = xmlStr + "\n\t\t\t<HEARINGPROGRESS>%s</HEARINGPROGRESS>" % myHearingProgressDIV.get_text().strip()
				
				myMovedRoom = currentRow.find('div', { "class" : "moved-highlight" })
				if myMovedRoom is not None:
					xmlStr = xmlStr + "\n\t\t\t<MOVEDROOM>%s</MOVEDROOM>" % myMovedRoom.get_text().strip()
				
				myTime = currentRow.find('td', { "class" : "not-before-time" })
				if myTime is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOTBEFORE>%s</NOTBEFORE>" % myTime.get_text().strip()
				myCaseNumber = currentRow.find('td', { "class" : "case-number" })
				if myCaseNumber is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber.get_text().strip().replace('*', '')

				myDefendants = currentRow.findAll('div', {"class" : "defendant-name-restricted-size-250"})
				xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
				for i,j in enumerate(myDefendants):
					xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
				xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"

				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"

		elif pageType == "Court Detail":
			myDetail = soup.find('table', { "class" : "non-scrolling-results" })
			
			myJudge = soup.find('td', { "class" : "judge" }).get_text().strip()
			myType = soup.find('td', { "class" : "hearing-description" }).get_text().strip()
			myCaseNumber = soup.find('td', { "class" : "case-number" }).get_text().strip()
			
			xmlStr = xmlStr + "\n\t<ROOM>\n\t\t<DETAIL>"
			if myJudge is not None:
				xmlStr = xmlStr + "\n\t\t\t<JUDGE>%s</JUDGE>" % myJudge
			
			if myType is not None:
				xmlStr = xmlStr + "\n\t\t\t<TYPE>%s</TYPE>" % myType
			
			if myCaseNumber is not None:
				xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber
				
			# the progress time in buried at the end of the td of class "case-progress-time" separated by <br/> ; need last 
			progressTime = soup.find('td', { "class" : "case-progress-time" })
			if progressTime is not None:
				strProgressTime = ''
				for a in progressTime.childGenerator():
					if ':' in str(a):
						strProgressTime = str(a)
				
				xmlStr = xmlStr + "\n\t\t\t<PROGRESS>"
				xmlStr = xmlStr + "\n\t\t\t\t<TIME>%s</TIME>" % strProgressTime.strip()
				xmlStr = xmlStr + "\n\t\t\t\t<MESSAGE>%s</MESSAGE>" % soup.find('td', { "class" : "case-progress-status" }).get_text().strip()
				xmlStr = xmlStr + "\n\t\t\t</PROGRESS>"
			
			myDefendants = soup.findAll('div', {"class" : "defendant-name-restricted-size"})
			myNotices = soup.findAll('td', {"class" : "public-notice"})
			
			xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
			for i,j in enumerate(myDefendants):
				xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
			xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"
			xmlStr = xmlStr + "\n\t\t\t<NOTICES>"
			for i,j in enumerate(myNotices):
				xmlStr = xmlStr + "\n\t\t\t\t<NOTICE>%s</NOTICE>" % j.get_text().strip()
			xmlStr = xmlStr + "\n\t\t\t</NOTICES>"
			
			xmlStr = xmlStr + "\n\t\t</DETAIL>\n\t</ROOM>\n"

		elif pageType == "Daily List":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"
				
				myCourt = currentRow.find('td', { "class" : "court-room-name" })
				if myCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<ROOM>%s</ROOM>" % myCourt.get_text().strip()
				
				myJudge = currentRow.find('td', { "class" : "judge" })
				if myJudge is not None:
					xmlStr = xmlStr + "\n\t\t\t<NAME>%s</NAME>" % myJudge.get_text().strip()
				
				myType = currentRow.find('td', { "class" : "hearing-description" })
				if myType is not None:
					xmlStr = xmlStr + "\n\t\t\t<TYPE>%s</TYPE>" % myType.get_text().strip()
				
				myTime = currentRow.find('td', { "class" : "not-before-time" })
				if myTime is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOTBEFORE>%s</NOTBEFORE>" % myTime.get_text().strip()
				
				myCaseNumber = currentRow.find('span', { "class" : "case-number" })
				if myCaseNumber is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber.get_text().strip().replace('*', '')
				
				myCaseTitle = currentRow.find('span', { "class" : "case-title" })
				myDefendants = currentRow.findAll('div', {"class" : "defendant-name-restricted-size-250"})

				if myCaseTitle is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASETITLE>%s</CASETITLE>" % myCaseTitle.get_text().strip()
				elif myDefendants is not None:
					xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
					for i,j in enumerate(myDefendants):
						xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
					xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"

				if ('*' in myCaseNumber.get_text()):
					xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>TRUE</REPORTRESTRICTIONS>"
				else:
					xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>FALSE</REPORTRESTRICTIONS>"
				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"
			
		# Screen 6. Jury Current Status
		elif pageType == "Jury Current Status":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"
				# court room
				myCourt = currentRow.find('td', { "class" : "court-room-name" })
				if myCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<ROOM>%s</ROOM>" % myCourt.get_text().strip()
				# judge
				myJudge = currentRow.find('td', { "class" : "judge" })
				if myJudge is not None:
					xmlStr = xmlStr + "\n\t\t\t<NAME>%s</NAME>" % myJudge.get_text().strip()
				# case number
				myCaseNumber = currentRow.find('td', { "class" : "case-number" })
				if myCaseNumber is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber.get_text().strip().replace('*', '')
					if ('*' in myCaseNumber.get_text()):
						xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>TRUE</REPORTRESTRICTIONS>"
					else:
						xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>FALSE</REPORTRESTRICTIONS>"

				# case title
				myCaseTitle = currentRow.find('td', { "class" : "case-title" })
				if myCaseTitle is not None:
					xmlStr = xmlStr + "\n\t\t\t<CASETITLE>%s</CASETITLE>" % myCaseTitle.get_text().strip()
				# name
				myDefendants = currentRow.findAll('div', {"class" : "defendant-name-restricted-size-250"})
				xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
				for i,j in enumerate(myDefendants):
					xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
				xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"
				# status
				myStatus = currentRow.find('td', { "class" : "hearing-description"})
				if myStatus is not None:
					xmlStr = xmlStr + "\n\t\t\t<STATUS>%s</STATUS>" % myStatus.get_text().strip()
				# not before
				myTime = currentRow.find('td', { "class" : "not-before-time" })
				if myTime is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOTBEFORE>%s</NOTBEFORE>" % myTime.get_text().strip()
					
				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"
		
		# Screen 7. All Court Status
		elif pageType == "All Court Status":
			myScrollingList = soup.find('table', { "class" : "results" })
			myRows = myScrollingList.find('tbody').find_all('tr')
			xmlStr = xmlStr + "\n\t<TABLE>"
			for currentRow in myRows:
				xmlStr = xmlStr + "\n\t\t<COURTCASE>"
				
				# court room
				myCourt = currentRow.find('td', { "class" : "court-room-name" })
				if myCourt is not None:
					xmlStr = xmlStr + "\n\t\t\t<ROOM>%s</ROOM>" % myCourt.get_text().strip()
				# no information
				myNoInformation = currentRow.find('td', { "class" : "no-information-row"})
				if myNoInformation is not None:
					xmlStr = xmlStr + "\n\t\t\t<NOINFORMATION>%s</NOINFORMATION>" % myNoInformation.get_text().strip()
				else:
					# case number
					myCaseNumber = currentRow.find('td', { "class" : "case-number" })
					if myCaseNumber is not None:
						xmlStr = xmlStr + "\n\t\t\t<CASENO>%s</CASENO>" % myCaseNumber.get_text().strip().replace('*', '')
						if ('*' in myCaseNumber.get_text()):
							xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>TRUE</REPORTRESTRICTIONS>"
						else:
							xmlStr = xmlStr + "\n\t\t\t<REPORTRESTRICTIONS>FALSE</REPORTRESTRICTIONS>"
					#name
					myDefendants = currentRow.findAll('div', {"class" : "defendant-name-restricted-size-250"})
					xmlStr = xmlStr + "\n\t\t\t<DEFENDANTS>"
					for i,j in enumerate(myDefendants):
						# only build <DEFENDANT> if there is at least one defendant listed
						if j.get_text().strip() != "":
							xmlStr = xmlStr + "\n\t\t\t\t<DEFENDANT>%s</DEFENDANT>" % j.get_text().strip()
						else:
							logging.debug("myDefendants j none")
					xmlStr = xmlStr + "\n\t\t\t</DEFENDANTS>"
					# status
					myStatus = currentRow.find('td', { "class" : "live-status"})
					if myStatus is not None:
						xmlStr = xmlStr + "\n\t\t\t<STATUS>%s</STATUS>" % myStatus.get_text().strip()
				
				xmlStr = xmlStr + "\n\t\t</COURTCASE>"
			xmlStr = xmlStr + "\n\t</TABLE>"
			
	except:
		# an error occurred extracting
		global error, errorMsg, errorCode
		error = True
		errorMsg = sys.exc_info()
		errorCode = 'XHIBIT_XML'
		
		# reset the page XML
		xmlStr = None
		
		if displayError:
			logging.exception("XHIBIT page parsing")
		
	return xmlStr

# returns the database row contents on success or None of error
def parseDB(macAddress):
	logging.debug("parseDB")
	cduRow = None
	connection = None
	global config
	
		
	#=============================================
	#              CONNECTING TO DB
	#=============================================
	#only open db related files/connection/cursor if the MAC address is formated correctly as a parameter
	try:
		#get the information needed to connect to the database from the .ini file parameter
		dbIP = config['DATABASE'].get('DBConn')			# DBconn is in the format "mysql:host=localhost"
		#if dbIP.startswith('\"') :
		dbIP = dbIP.strip('"').split('=')[1]
		dbName = config['DATABASE'].get('DBName')
		username = config['DATABASE'].get('DBusername')
		passwd = config['DATABASE'].get('DBpasswd')

		logging.debug("*** Connecting on host [{0}] to database [{1}] with username/password [{2}/{3}] ***".format(dbIP, dbName, username, passwd))
		
		# open a database connection
		connection = pymysql.connect(host=dbIP, user=username, password=passwd, db=dbName, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
		# prepare a cursor object using cursor() method
		cursor = connection.cursor()
		#find the cdu with the MAC address passed to the script - using SQL aliases to name obtuse columns, using a "IFNULL" condition
		#  to decide the priority of the XSL from either CDU or SITE
		logging.debug("database mac %s" % macAddress.upper())
		sql = "SELECT CDU.title as title, location, notification, macAddress, url, refresh, SITE.alert, SITE.title as site, SITE.pageUrl as pageUrl, IFNULL(CDU.xsl, SITE.xsl) as xsl, SITE.powersaveSchedule FROM CDU, SITE WHERE CDU.fkSITE = SITE.id AND UPPER(CDU.macAddress)='" + macAddress.upper() + "'"
		# execute the SQL query using execute() method.
		logging.debug("SQL: %s" % sql)
		cursor.execute(sql)
		# fetch all of the rows from the query
		data = cursor.fetchall()
		# close the cursor object
		cursor.close()
		
		# now check the results of data - there must be one row and one row only
		if cursor.rowcount == 1:
			cduRow = data[0]
		else: 
			logging.error("Row count > 1")
		logging.debug("data: %s" % data[0])
		logging.debug("cduRow: %s" % cduRow)
	except:
		global error, errorMsg, errorCode
		error = True
		errorMsg = sys.exc_info()
		errorCode = 'DB_CONNECT'
		#print(sys.exc_info())
		
		if displayError:
			logging.exception("XHIBIT page parsing")
		
	finally:
		# close the connection
		if connection is not None:
			connection.close()
		#we close the cursor and connection immediately after fetching the data to release expensive database connections
		
	return cduRow;

# returns dictionary of results:
# xml: is the formatted XML
# url: is the index URL
# pageUrl: is the base URL
def formatCDU(row):
	global pageIsEnglish
	try:
		myUrl = row['url']
		myPageUrl = row['pageUrl']
		xmlStr = ""
		
		xmlStr = xmlStr + "\n\t<CDU>"
		
		xmlStr = xmlStr + "\n\t\t<VERSION>%s</VERSION>" % CONST_VERSION
		xmlStr = xmlStr + "\n\t\t<SITE-TITLE>%s</SITE-TITLE>" % row['site']
		xmlStr = xmlStr + "\n\t\t<TITLE>%s</TITLE>" % row['title']
		xmlStr = xmlStr + "\n\t\t<LOCATION>%s</LOCATION>" % row['location']
		xmlStr = xmlStr + "\n\t\t<MAC-ADDR>%s</MAC-ADDR>" % row['macAddress'].upper()
		xmlStr = xmlStr + "\n\t\t<NOTICE>"
		if (row['notification'] != None):
			xmlStr = xmlStr + row['notification']
		xmlStr = xmlStr + "\n\t\t</NOTICE>"
		
		# decode the JSON
		powersave = False
		powersaveSchedule = json.JSONDecoder().decode(row['powersaveSchedule'])
		powersave = iterateSchedules(powersaveSchedule)
		if powersave:
			xmlStr = xmlStr + "\n\t\t<POWER-SAVING>ENABLED</POWER-SAVING>"
		else:
			xmlStr = xmlStr + "\n\t\t<POWER-SAVING>DISABLED</POWER-SAVING>"

		xmlStr = xmlStr + "\n\t\t<REFRESH>%s</REFRESH>" % str(row['refresh'])
		xmlStr = xmlStr + "\n\t\t<URL>%s</URL>" % row['url']
		xmlStr = xmlStr + "\n\t\t<XSL>%s</XSL>" % row['xsl']

		xmlStr = xmlStr + "\n\t</CDU>"

	except:
		# an error occurred extracting
		global error, errorMsg, errorCode
		error = True
		errorMsg = sys.exc_info()
		errorCode = 'CDU_XML'
		
		if displayError:
			logging.exception("XHIBIT page parsing")
	
	return xmlStr, myUrl, myPageUrl;
	
# this function takes the index and page URLs extracted from database, along with the current page index if defined
#  returns a full site and an updated page index
def formatUrl(url, pageUrl, currentPageIndex, dataRefresh):
	fullURL = ""
	
	try:
		#url = "http://localhost/xhibit2/xhibit/all_court_status.html" #all court URL
		#url = "http://localhost/xhibit2/xhibit/jury_current_status.html" # jury screen URL
		#url = "http://localhost/xhibit2/xhibit/CCC_foyer_09092015_List1.html"
		# URL is the SITE.pageUrl in addition to the CDU.url - but the CDU.url needs to be URL encoded.

		# the URL can be a semi colon delimited list of URLs. In which case, there is a need to
		#  extract the "current page" parameter
		myURLs = url.split(";")
		#print(myURLs)
		logging.debug(myURLs)
				
		if len(myURLs) == 1:
			# there is only one URL, so use it
			thisUrl = myURLs[0]
		else:
			# there is more than one URL
			if currentPageIndex == None:
				# there is no current page argument passed to script, so assume the first page
				logging.debug("No current Page URL, so assuming the first\n")
				urlIndex = 0
			else:
				# current page is defined, so the url is the next one in the list - but not past the end of the array index
				#   only if not refreshing the current data
				if dataRefresh is None:
					logging.debug("Current Page Index (" + str(currentPageIndex) + ") so looking for the next\n")
					urlIndex = (currentPageIndex + 1) % len(myURLs)
				else:
					urlIndex = (currentPageIndex) % len(myURLs)
			
			thisUrl = myURLs[urlIndex]
			logging.debug("urlIndex: " + str(urlIndex) + ", Next Url: " + thisUrl + "\n")
			currentPageIndex = urlIndex

		encodedUrl = urllib.parse.urlencode({'uri':thisUrl})
		fullURL = pageUrl + encodedUrl
		#fullURL = url
		#print("Full URL: " + fullURL)
		logging.debug("Full URL: " + fullURL)

	except:
		# an error occurred extracting
		global error, errorMsg, errorCode
		error = True
		errorMsg = sys.exc_info()
		errorCode = 'CDU_XML'
		
		if displayError:
			logging.exception("XHIBIT page parsing")
	
	return currentPageIndex, fullURL

def writeToSyslog(syslogMessage):
	logging.debug("writeToSysLog: " + syslogMessage)
	if (platform.system() != "Windows"):
		syslog.openlog(ident="xhibit.py", logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL5);
		syslog.syslog(syslog.LOG_ERR, syslogMessage);
		syslog.closelog();
	
def logError(macAddress, currentPageIndex, errorCode, errorMsg, url, xhibitResponse):
	cduRow = None
	connection = None
	global config
	
	sysLogMessage = "Error (%s) %s. MAC Addr (%s)." % (errorCode, errorMsg, macAddress)
	
	if currentPageIndex is not None:
		sysLogMessage = sysLogMessage + " Page Index (%d)." % currentPageIndex
	if url is not None:
		sysLogMessage = sysLogMessage + " URL (%s)." % url

	logging.error(sysLogMessage)
	writeToSyslog(sysLogMessage)		
	
	if xhibitResponse is not None:
		logging.debug("Xhibit Response: " + xhibitResponse + "\n")		

	return

macAddress = sys.argv[1]
iniLoc = sys.argv[2]
cduOnly = int(sys.argv[3])
if len(sys.argv) > 4:
	try:
		currentPageIndex = int(sys.argv[4])
	except:
		currentPageIndex = None
else:
	currentPageIndex = None
if len(sys.argv) > 5:
	dataRefresh = int(sys.argv[5])
else:
	dataRefresh = None

errorUrl = None
errorXhibitResponse = None

#read the ini file with a config parser
displayError = False
try:
	config = configparser.ConfigParser()
	config.read(iniLoc)
	logging.debug("ini file: " + iniLoc)
	try:
		configDisplayError = int(config['ERROR'].get('DisplayError'))
		if configDisplayError == 1:
			displayError = True
	except:
		# do nothing
		A=1
except:
	error = True
	errorMsg = sys.exc_info()
	errorCode = 'CONFIG_FILE'
	config = None

#check the format of the MAC and only proceed with database extraction if correct format
macFormat = re.compile('.{2}:.{2}:.{2}:.{2}:.{2}:.{2}')
macValid = macFormat.match(macAddress)
logging.debug("macValid: %s" % macValid)
if macValid:
	logging.debug("macValid true")
else:
	logging.debug("macValid false")

if not error and (macValid and os.path.isfile(iniLoc)):
	logging.debug("not error and mac valid and ini")
	
	cduXML = ''
	pageXML = ''
	contentsXML = ''
	
	cdu = parseDB(macAddress)
	if not error and (cdu is not None):
		# format the CDU XML using contents from database; returns the XML, the index URL and page URL
		cduXML, url, pageUrl = formatCDU(cdu)
		logging.debug("CDU XML " + cduXML + "\n")
		logging.debug("URL " + url + "\n")
		logging.debug("Page ULR " + pageUrl + "\n")
		
		if not error:
			# obtain the site URL to fetch
			logging.debug("Getting URL to fetch")
			currentPageIndex, siteUrl = formatUrl(url, pageUrl, currentPageIndex, dataRefresh)
			#if currentPageIndex is not None:
			#	print("Current Page Index " + currentPageIndex + "\n")
			#print("Site Url " + siteUrl + "\n")
			# capture the index URL - in case need for error reporting
			errorUrl = url
		if not error and not cduOnly:
			logging.debug("fetching XHIBIT page")
			# now fetch the XHIBIT page
			try:
				logging.debug("fetching XHIBIT page")
				logging.debug("siteUrl: " + siteUrl)
				xhibitContents = urllib.request.urlopen(siteUrl)
				logging.debug("type: " + type(xhibitContents).__name__)
				#print (xhibitContents.read()) # commenting out fixes none error

				if not error:
					# now parse the XHIBIT contents
					try:
						soup = BeautifulSoup(xhibitContents, "html.parser")
						#logging.debug("Xhibit Contents prettified: " + soup.prettify() + "\n")
						# capture the XHIBIT response for error logging
						errorXhibitResponse = soup.prettify()[:4500]
					except:
						error = True
						errorMsg = sys.exc_info()
						errorCode = 'BEAUTIFUL_SOUP_PARSER'
				
				if not error:
					# first extract the page detail
					logging.debug("Attempting to extract details")
					pageType, pageXML = formatPageXML(soup, currentPageIndex, url)
					logging.debug(pageType)
					logging.debug(pageXML)
				
				if not error:
					# now parse the XHIBIT XML based on the type of page
					contentsXML = formatXhibitXML(soup, pageType)
					#print("Contents XML:")
					logging.debug(contentsXML)

			except:
				error = True
				errorMsg = sys.exc_info()
				errorCode = 'XHIBIT_FETCH' ## error
					
		if not error:
			# now format the full XML to return
			logging.debug("Printing full XML to file")
			fullXML = formatXML(cduXML, pageXML, contentsXML)
			print (fullXML)
			# print just XML to file 
			#f = open('output.xml','w')
			#f.write(fullXML)
			#f.close
			#logging.debug(fullXML)
		
	elif not error:
		error = True
		errorMsg = 'Unknown CDU matching %s' % macAddress
		errorCode = 'MAC-ADDRESS-UNKNOWN'

elif not error:
    error = True
    errorMsg = 'MAC Address or Ini file not valid'
    errorCode = 'MAC-ADDRESS-INVALID'

# check for errors
if error:
	#print("Display Error: (" + str(displayError) + ")\n")
	# log error
	logError(macAddress, currentPageIndex, errorCode, str(errorMsg), errorUrl, errorXhibitResponse)
	
	if displayError:
		logging.error("Error occurred: (%s) %s\n" % (errorCode, errorMsg))
		
