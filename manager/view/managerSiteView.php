<?php
/*
 * managerIndexView.php
 * 
 * This is the view (MVC) for index dynamic page. It renders the
 *  data obtained from the Model, in response to processing request via
 *  the controller.
 */
require_once "controller/managerController.php";

class ManagerSiteView {
	private $controller;
	
	private $SITEindex;
	private $thisSite;
	private $authenticatedUser;
	private $selectorURL;
	private $pageURL;

	function __construct($controller) {
		$this->controller = $controller;
		$this->authenticatedUser = $this->controller->getAuthenticatedUser();
		if (is_null($this->authenticatedUser)) {
			return;
		}
		
		$this->SITEindex = $controller->getSITEindex();		
		$this->thisSite = $controller->getCurrentSite();
		if (NULL != $this->thisSite) {
			$this->title = $this->thisSite['title'];
			$this->xsl = $this->thisSite["xsl"];
			
			if ($this->thisSite["alert"] == NULL) {
				$this->alert = 'undefined';
			} else {
				$this->alert = $this->thisSite["alert"];
			}

		}
		$this->selectorURL = $this->thisSite["selectorUrl"];
		$this->pageURL = $this->thisSite["pageUrl"];
		$this->powersaveSchedule = $this->thisSite["powersaveSchedule"];
	}
	
	//public function display() {}
	function display() {
	
echo <<<START
	<div id="title">
		<!--<img src="images/smartTV_web.jpg">-->
		<a href="index.php">Home</a>
		<h1><i class="fa fa-desktop"></i>
		SITE ($this->title:$this->SITEindex)</h1>
	</div>

START;

		if (isset($this->authenticatedUser)) {
			echo <<<USER
	<p class="user">User is <span class="username">$this->authenticatedUser</span></p>
USER;
		} else {
			// not authenticated to do not continue
			return;
		}
	
echo <<<CDU
	<section id="listofCDUS">
CDU;
		if ($this->controller->isErr()) {
			print("\t<p class=\"error\">Error: " . $this->controller->sErr() . "</p>\n");
		}
		else {
			print("\t\t<section id=\"info\">\n\n");
				
				print("\t\t\t<table class=\"output\">\n");
				foreach ($this->controller->sOut() as $currentOutputLine) {
					print("\t\t\t<tr><td class=\"output\">$currentOutputLine</td></tr>\n");
				}
				print("\t\t\t</table>\n</section><br/>\n");
				
				//print_r($this->thisSite);
				if (!is_null($this->thisSite)) {
									
					echo <<<SITE
<br/><br/>
<section id="SITE">
	<center>
	<form id="site" name="site" method="post" action="site.php">
		<input type="hidden" name="id" value="$this->SITEindex"/>
		<table class="results">
			<tr><th>Title</th><th>XSL</th><th>Alert</th></tr>
			<tr>
				<td class="results"><input type="text" name="title" size="30" maxlength="30" value="$this->title"/></td>
				<td class="results">
					<!--<input type="text" name="xsl" size="30" maxlength="50" value="$this->xsl"/>-->
					<select name="xsl" autocomplete="off">
SITE;
						if (strcmp($this->xsl, 'old') == 0) {
							print("<option selected value=\"old\">Current</option>");
						} else {
							print("<option value=\"old\">Current</option>");
						}
						if (strcmp($this->xsl, 'new') == 0) {
							print("<option selected value=\"new\">New</option>");
						} else {
							print("<option value=\"new\">New</option>");
						}
						
					echo <<<SITE
					</select>
				</td>
				<td class="results"><textarea name="alert" rows="10" cols="50">$this->alert</textarea></td>
			</tr>
			
			<tr>
				<th colspan="3">Selector URL</th>
			</tr>
			<tr>
				<td colspan="3"><input type="input" name="selectorURL" size="60" value="$this->selectorURL"/></td>
			</tr>
			<tr>
				<th colspan="3">Page URL</th>
			</tr>
			<tr>
				<td colspan="3"><input type="input" name="pageURL" size="120" value="$this->pageURL"/></td>
			</tr>
			<tr>
				<th colspan="3">PowerSave Schedule</th>
			</tr>
			<tr>
				<td colspan="3"><textarea name="powersaveSchedule" rows="20" cols="120">$this->powersaveSchedule</textarea></td>
			</tr>
			<tr><td colspan="3"><input type="submit" name="UpdateSite" value="Update"/></tr>
		</table>
	</form>
	</center>
</section>
SITE;
				}
		}
		
echo <<<END
END;
	}

}
?>