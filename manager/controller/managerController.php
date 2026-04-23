<?php
/*
 * ManagerIndexController.php
 *
 * This is the controller for index dynamic page.
 *
 * It reads configuration from INI file, which includes database configuration
 *  parameters.
 *
 * It invokes the model to retrieve data to parse through the view.
 */

require_once "model/site.php";
require_once "model/cdu.php";
require_once "model/DB/managerCDUDB.php";
require_once "model/DB/managerSiteDB.php";
require_once "model/DB/managerAuditDB.php";
require_once "lib/nusoap.php";

define("OPS_INI", "ops.ini");

define("INI_USE_DB", "UseDB");
define("INI_DB_CONN", "DBConn");
define("INI_DB_NAME", "DBName");
define("INI_DB_TYPE", "DBType");
define("INI_DB_USERNAME", "DBusername");
define("INI_DB_PASSWD", "DBpasswd");
define("INI_MAX_RECORD_COUNT", "MaxRecordCount");

define("SHOW_PROGRESS", "ShowProgress");

define("HTTP_ID", "id");
define("HTTP_SITE_FORM_DETAILS", "UpdateSite");
define("HTTP_CDU_FORM_DETAILS", "UpdateCDU");
define("HTTP_CDU_FORM_NOTIFICATION_UPDATE", "UpdateNotice");
define("HTTP_CDU_FORM_NOTIFICATION_CANCEL", "CancelNotice");

define("HTTP_TITLE", "title");
define("HTTP_DESCRIPTION", "description");
define("HTTP_LOCATION", "location");
define("HTTP_MAC_ADDRESS", "macAddress");
define("HTTP_REFRESH", "refresh");
define("HTTP_URL", "url");
define("HTTP_BASEURL", "baseurl");
define("HTTP_XSL", "xsl");
define("HTTP_ALERT", "alert");
define("HTTP_NOTICE", "notification");
define("HTTP_IP_ADDR", "notification");
define("HTTP_SELECTOR_URL", "selectorURL");
define("HTTP_PAGE_URL", "pageURL");
define("HTTP_POWERSAVE_SCHEDULE", "powersaveSchedule");

define("URI_INDEX", "id");

define("REMOTE_USER", "REMOTE_USER");
define("PHP_USER", "PHP_AUTH_USER");

define("AUDIT_FETCH_CDUS", "FETCHING_CDUS");
define("AUDIT_FETCH_SITES", "FETCH_SITE");
define("AUDIT_UPDATE_SITE", "UPDATE_SITE");
define("AUDIT_FETCH_CDU", "FETCH_CDU");
define("AUDIT_UPDATE_CDU", "UPDATE_CDU");
define("AUDIT_RESET_NOTIFICATION", "RESET_NOTIFICATION");
define("AUDIT_UPDATE_NOTIFICATION", "UPDATE_NOTIFICATION");


class ManagerController {
	private $writeToDB;
	private $DBconn;
	private $DBtype;
	private $DBusername;
	private $DBpasswd;
	private $MaxRecordCount;
	private $showProgress;

	private $outputLog;	// array of string
	private $strErr;
	
	private $CDUs;
	private $currentCDU;
	private $CDUid;
	private $CDUipAddr;
	private $myCDUipHistory;
	
	private $SITEid;
	private $currentSite;
	private $selectorURL;
	private $pageURL;
	
	private $arrayOfValues;
	private $arrayOfIndexes;

	
	private $authenticatedUser;

	function __construct() {
		// initialise state
		$this->outputLog = NULL;
		$this->strErr = NULL;
		
		$this->writeToDB = FALSE;
		$this->DBconn = NULL;
		$this->DBtype = NULL;
		$this->DBusername = NULL;
		$this->DBpasswd = NULL;
		$this->MaxRecordCount = NULL;
		
		$this->CDUs = NULL;
		$this->currentCDU = NULL;
		$this->CDUid = NULL;
		$this->CDUipAddr = NULL;
		$this->myCDUipHistory = NULL;

		$this->SITEid = NULL;
		$this->currentSite = NULL;
		$this->selectorURL = "";
		$this->pageURL = "";
		
		$this->arrayOfValues = array();
		$this->arrayOfIndexes = array();
		
		$this->showProgress = FALSE;
		
		$this->authenticatedUser = NULL;

		$this->parseIni();
		
		//$this->extractParameters();
	}

	// extracts parameters passed in the request URL to control state
	// NOTE - Request parameters override defaults
	private function extractParameters() {
		// check if needing to write to database
		if (defined($_GET[URI_INDEX])) {
			$uriID =(int) $_GET[URI_INDEX];
		}
	}

	private function dbConn() {
		return $this->DBconn;
	}
	private function dbType() {
		return $this->DBtype;
	}
	private function dbUsername() {
		return $this->DBusername;
	}
	private function dbPasswd() {
		return $this->DBpasswd;
	}
	
	// returns true if error has been set otherwise false
	function isErr() {
		$retVal = FALSE;
		if (strlen($this->strErr) > 0) {
			$retVal = TRUE;
		}
		return $retVal;
	}
	function sErr() {
		return $this->strErr;
	}
	
	// returns progress statements
	function sOut() {
		if ($this->showProgress) {
			return $this->outputLog;
		} else {
			return array();
		}
	}

	// parse local ini to control state
	private function parseIni() {
		try {
			// initial state is false, so only looking for true
			$iniValues = parse_ini_file(OPS_INI, FALSE, INI_SCANNER_RAW);
			//print_r($iniValues);
	
			// first database settings
			if (defined($iniValues[INI_USE_DB])) {
				if (strcasecmp($iniValues[INI_USE_DB], "true") == 0) {
					$this->writeToDB = TRUE;
				}
	
				$this->DBconn = trim($iniValues[INI_DB_CONN]);
				$this->DBconn = $this->DBconn . ";dbname=" . $iniValues[INI_DB_NAME];

				$this->DBtype = trim($iniValues[INI_DB_TYPE]);
				$this->DBusername = trim($iniValues[INI_DB_USERNAME]);
				$this->DBpasswd = trim($iniValues[INI_DB_PASSWD]);
				$this->MaxRecordCount = trim($iniValues[INI_MAX_RECORD_COUNT]);
			}
			
			if (strcasecmp($iniValues[SHOW_PROGRESS], "true") == 0) {
				$this->showProgress = TRUE;
			}

		} catch (Exception $ex) {
			// TODO: HANDLE error
		}
	}
	
	// this method is called to action the controller
	public function action($method) {
		$this->outputLog = array();
		
		// get the authenticated user - this is used for audit purposes
		if (isset($_SERVER[REMOTE_USER])) {
			$this->authenticatedUser = $_SERVER[REMOTE_USER];
		} elseif (isset($_SERVER[PHP_USER])) {
			$this->authenticatedUser = $_SERVER[PHP_USER];
		} else {
			// authenticated user is unknown, therefore do nothing
			return;
		}
		
		//print_r($_POST);
		$dbAuditModel = new ManagerAUDIT_DB($this->DBconn, $this->DBusername, $this->DBpasswd, $this->DBtype);
		
		if ((strlen($method) == 0) || (strcmp($method, "index") == 0)) {
			// audit the activity
			$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_FETCH_CDUS, '');
			
			array_push($this->outputLog, "Fetching list of CDUs");
			
			// retrieve list of CDUs from database
			$dbModel = new ManagerSITE_DB($this->DBconn, $this->DBusername, $this->DBpasswd, $this->DBtype);
			$myCDUs = $dbModel->fetchAll();
			if (FALSE !== $myCDUs) {
				$this->CDUs = $myCDUs;
				//print_r($CDUs);
			}
		} elseif (strcmp($method, "SITE") == 0) {
			array_push($this->outputLog, "Fetching SITE");

			// audit the activity
			$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_FETCH_SITES, '');
			
			// retrieve the SITE details - for given index
			$this->SITEid = $_GET[HTTP_ID];
			if (!isset($this->SITEid)) {
				$this->SITEid = $_POST[HTTP_ID];
				array_push($this->outputLog, "Get SITE [$this->SITEid] index from POST");				
			}
			
			$dbModel = new ManagerSITE_DB($this->DBconn, $this->DBusername, $this->DBpasswd, $this->DBtype);
			if (isset($_POST[HTTP_SITE_FORM_DETAILS])) {
				// submitted CDU details update
				array_push($this->outputLog, "Updating SITE with index [$this->SITEid]");
				
				//TODO: should verify all form values
				$myTitle = $_POST[HTTP_TITLE];
				$myXsl = $_POST[HTTP_XSL];
				$myAlert = $_POST[HTTP_ALERT];
				$mySelectorURL = $_POST[HTTP_SELECTOR_URL];
				$myPageURL = $_POST[HTTP_PAGE_URL];
				$powerSaveSchedule = $_POST[HTTP_POWERSAVE_SCHEDULE];
				
				// XSL can be empty
				if (strlen($myXsl) == 0) {
					$myXsl = NULL;
				}
				// alert can be empty r undefined
				if ((strlen($myAlert) == 0) || (strcmp($myAlert, 'undefined') == 0)) {
					$myAlert = NULL;
				}
				
				// audit the activity
				$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_UPDATE_SITE, $myTitle . ' | ' . $myXsl . ' | ' . $myAlert . ' | ' . $mySelectorURL . ' | '. $myPageURL);

				$status = $dbModel->fullUpdate($this->SITEid,
				                               $myTitle,
											   $myXsl,
											   $myAlert,
											   $mySelectorURL,
											   $myPageURL,
											   $powerSaveSchedule);
				if ($status !== FALSE) {
					array_push($this->outputLog, "....success.");
				}
			}

			if (is_numeric($this->SITEid) && ($this->SITEid > 0)) {
				array_push($this->outputLog, "... with index [$this->SITEid]");				
				$mySite = $dbModel->fetch($this->SITEid);
				if (FALSE !== $mySite) {
					$this->currentSite = $mySite;
					//print_r($this->currentSite);
				}
			}

		} elseif (strcmp($method, "CDU") == 0) {		
			array_push($this->outputLog, "Fetching CDU");
						
			// retrieve the CDU details - for given index
			$this->CDUid = $_GET[HTTP_ID];
			if (!isset($this->CDUid)) {
				$this->CDUid = $_POST[HTTP_ID];
				array_push($this->outputLog, "Get CDU [$this->CDUid] index from POST");				
			}

			// audit the activity
			$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_FETCH_CDU, "($this->CDUid)");

			// check to see if form is being submitted (POST)
			//  One of two forms:
			//     1. CDU details
			//     2. Notification
			
			$dbModel = new ManagerCDU_DB($this->DBconn, $this->DBusername, $this->DBpasswd, $this->DBtype);
			if (isset($_POST[HTTP_CDU_FORM_DETAILS])) {
				// submitted CDU details update
				array_push($this->outputLog, "Updating CDU with index [$this->CDUid]");
				
				//TODO: should verify all form values
				$myTitle = $_POST[HTTP_TITLE];
				$myDescription = $_POST[HTTP_DESCRIPTION];
				$myLocation = $_POST[HTTP_LOCATION];
				$myMacAddress = $_POST[HTTP_MAC_ADDRESS];
				$myRefresh = $_POST[HTTP_REFRESH];
				$myXsl = $_POST[HTTP_XSL];
				//$myBaseUrl = $_POST[HTTP_BASEURL];
				//$myUrl = $myBaseUrl . '/' . $_POST[HTTP_URL];
				$myUrl = $_POST[HTTP_URL];
				
				// XSL can be empty
				if (strlen($myXsl) == 0) {
					$myXsl = NULL;
				}
				
				// audit the activity
				$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_UPDATE_CDU, "($this->CDUid)" .
				                             ' | ' . $myTitle .
				                             ' | ' . $myDescription .
				                             ' | ' . $myLocation .
				                             ' | ' . $myMacAddress .
				                             ' | ' . $myRefresh .
				                             ' | ' . $myXsl .
											 ' | ' . $myUrl);

				$status = $dbModel->fullUpdate($this->CDUid,
				                               $myMacAddress,
				                               $myTitle,
				                               $myDescription,
				                               $myLocation,
				                               $myUrl,
											   $myXsl,
				                               $myRefresh);
				if ($status !== FALSE) {
					array_push($this->outputLog, "....success.");
				}
			}
			
			if (isset($_POST[HTTP_CDU_FORM_NOTIFICATION_UPDATE])) {
				// submitted Notification update
				array_push($this->outputLog, "Updating CDU notification with index [$this->CDUid]");

				//TODO: should verify all form values
				$myNotice = $_POST[HTTP_NOTICE];

				// audit the activity
				$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_UPDATE_NOTIFICATION, "($this->CDUid)" . ' | ' . $myNotice);

				$status = $dbModel->notificationUpdate($this->CDUid, $myNotice);
				if ($status !== FALSE) {
					array_push($this->outputLog, "....success.");
				}
			}
			if (isset($_POST[HTTP_CDU_FORM_NOTIFICATION_CANCEL])) {
				// submitted Notification update
				array_push($this->outputLog, "Cancelling CDU notification with index [$this->CDUid]");

				// audit the activity
				$dbAuditModel->newAudit($this->authenticatedUser, AUDIT_RESET_NOTIFICATION, "($this->CDUid)");

				$status = $dbModel->notificationUpdate($this->CDUid, NULL);
				if ($status !== FALSE) {
					array_push($this->outputLog, "....success.");
				}
			}

			if (is_numeric($this->CDUid) && ($this->CDUid > 0)) {
				array_push($this->outputLog, "... with index [$this->CDUid]");				
				$myCDU = $dbModel->fetch($this->CDUid);
				if (FALSE !== $myCDU) {
					$this->currentCDU = $myCDU;
					$this->CDUipAddr = $this->currentCDU['ipAddr'];
					//print_r($this->currentCDU);
				}
				
				$myCDUipHistory = $dbModel->fetchIpHistory($this->CDUid, $this->MaxRecordCount);
				if (FALSE !== $myCDUipHistory) {
					$this->myCDUipHistory = $myCDUipHistory;
					//print_r($this->myCDUipHistory);
				}
				
				// now need to fetch the list of available pages
				$this->getAvailablePages($dbModel);
			}
		}
				
		if (!$dbModel->isErr()) {
			$this->outputLog = array_merge($this->outputLog, $dbModel->sProgress());
		} else {
			$this->strErr = $dbModel->sErr();
		}
	}
	
	// returns the current list of CDUs
	public function getCDUs() {
		return $this->CDUs;
	}
	
	public function getCDUindex() {
		return $this->CDUid;
	}
	
	public function getCurrentCDU() {
		return $this->currentCDU;
	}
	
	public function getCurrentCDUip() {
		return $this->CDUipAddr;
	}
	
	public function getCurrentCDUipHistory() {
		return $this->myCDUipHistory;
	}
	
	public function getSITEindex() {
		return $this->SITEid;
	}
	public function getCurrentSite() {
		return $this->currentSite;
	}
	
	public function getAuthenticatedUser() {
		return $this->authenticatedUser;
	}
	
	public function getSelectorURL() {
		return $this->selectorURL;
	}
	public function getPageURL() {
		return $this->pageURL;
	}

	private function getAvailablePages($dbModel) {
		// get the selector Base URL from associated site
		$mySiteSelectorURL = $dbModel->fetchSelectorURL($this->CDUid);
		
		if (FALSE !== $mySiteSelectorURL) {
			//print("Selector URL ($mySiteSelectorURL)");
		
			$selectorHTML = file_get_contents($mySiteSelectorURL);

			//print($selectorHTML);
			$selectorHTMLArray = explode("\n", $selectorHTML);

			//print_r($selectorHTMLArray);

			// find all the rows having display-location
			// array preg_grep ( string $pattern , array $input [, int $flags = 0 ] )
			$displayLocations = preg_grep("/.*class=\"display-location.*|.*onClick='selectDisplay.*/", $selectorHTMLArray);
			//print_r($displayLocations);

			foreach ($displayLocations as $currentRow) {
				if (preg_match("/class=\"display-location\"/", $currentRow)) {
					//print("Current Row: $currentRow\n");
					
					$startPos = strpos($currentRow, '>');
					//print ("Start Position: $startPos");
					
					$endPos = strpos($currentRow, '<', $startPos+1);
					//print (" End Position: $endPos\n");
					
					$newRow = substr($currentRow, $startPos+1, $endPos-($startPos+1));
					//print("New Row: $newRow\n");
					$this->arrayofIndexes[] = $newRow;
				}

				if (preg_match("/selectDisplay/", $currentRow)) {
					//print("Current Row: $currentRow\n");
					
					$startPos = strpos($currentRow, 'selectDisplay(');
					//print ("Start Position: $startPos");
					
					$endPos = strpos($currentRow, ')', $startPos+15);
					//print (" End Position: $endPos\n");
					
					$newRow = substr($currentRow, $startPos+15, $endPos-($startPos+16));
					//print("New Row: $newRow\n");
					$this->arrayOfValues[] = $newRow;
				}
				
			}

			//print_r($this->arrayofIndexes);
			//print_r($this->arrayOfValues);
		}
	}
	
	public function getArrayOfSitePagesIndexes() {
		return $this->arrayofIndexes;
	}
	public function getArrayOfSitePagesValues() {
		return $this->arrayOfValues;
	}
}
?>
