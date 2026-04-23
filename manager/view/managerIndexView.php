<?php
/*
 * managerIndexView.php
 * 
 * This is the view (MVC) for index dynamic page. It renders the
 *  data obtained from the Model, in response to processing request via
 *  the controller.
 */
require_once "controller/managerController.php";

class ManagerIndexView {
	private $controller;
	private $authenticatedUser;

	function __construct($controller) {
		$this->controller = $controller;		
		$this->authenticatedUser = $this->controller->getAuthenticatedUser();
	}

	//public function display() {}
	function display() {
echo <<<START
	<div id="title">
		<!--<img src="images/marketing-manager.jpg">-->
		<h1><i class="fa fa-camera-retro fa-2x"></i>
		XHIBIT Display Manager</h1>
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
			print("\t\t<section id=\"CDUlist\">\n\n");
				
				print("\t\t\t<table class=\"output\">\n");
				foreach ($this->controller->sOut() as $currentOutputLine) {
					print("\t\t\t<tr><td class=\"output\">$currentOutputLine</td></tr>\n");
				}
				print("\t\t\t</table><br/>\n");
				
				//print_r($this->controller->getCDUs());
				if (!is_null($this->controller->getCDUs())) {
					// first need to get a list of Unique Site IDs/Title - this will form the
					$mySites = array();
					$mySiteID = 0;
					foreach ($this->controller->getCDUs() as $currentRow) {
						if ($mySiteID != $currentRow["SITEid"]) {
							// we have a new site
							array_push($mySites, $currentRow);
							$mySiteID = $currentRow["SITEid"];
						}
					}
				
					print("\t\t\t<center><table class=\"results\">\n");
					print("\t\t\t\t<th>Site</th><th>CDUs</th>\n");
					//foreach ($this->controller->getCDUs() as $currentRow) {
					foreach ($mySites as $currentSite) {
						print("\t\t\t\t<tr>\n");
						print("\t\t\t\t\t<td class=\"results\"><a href=\"site.php?id=" . $currentSite["SITEid"] . "\">" . $currentSite["site"] . "</a></td>\n");
						print("\t\t\t\t\t<td class=\"results\">\n");
						foreach ($this->controller->getCDUs() as $currentCDU) {
							if ($currentSite["SITEid"] == $currentCDU["SITEid"]) {
								print("\t\t\t\t\t\t<a href=\"cdu.php?id=" . $currentCDU["CDUid"] . "\">" . $currentCDU["title"] . "</a><br/>\n");
							}
						}
						print("\t\t\t\t\t</td>\n");
						print("</tr>\n");
					}
					print("\t\t\t</table></center>\n");
				}
				print("\t\t</section>\n");
		}
		
echo <<<END
		</section>
END;
	}

}
?>