<?php
/*
 * managerIndexView.php
 * 
 * This is the view (MVC) for index dynamic page. It renders the
 *  data obtained from the Model, in response to processing request via
 *  the controller.
 */
require_once "controller/managerController.php";

define("OPS_INI", "ops.ini");
define("XHIBIT_LOCATION", "location");
define("PROXY_LOCATION", "proxy");
define("CDU_LOCATION", "cdu");
define("XHIBIT_URL", "url");

class ManagerCDUView {
	private $controller;
	
	private $CDUindex;
	private $thisCDU;
	private $CDUsite;
	private $CDUip;
	private $xhibitLocation;
	private $authenticatedUser;

	function __construct($controller) {
		$this->controller = $controller;
		
		$this->authenticatedUser = $this->controller->getAuthenticatedUser();
		if (is_null($this->authenticatedUser)) {
			return;
		}
		
		$this->CDUindex = $controller->getCDUindex();
		$this->CDUip = urlencode($controller->getCurrentCDUip());
				
		$this->thisCDU = $controller->getCurrentCDU();
		if (NULL != $this->thisCDU) {
			$this->CDUsite = $this->thisCDU['site'];
			$this->title = $this->thisCDU["title"];
			$this->description = $this->thisCDU["description"];
			$this->location = $this->thisCDU["location"];
			$this->macAddress = $this->thisCDU["macAddress"];
			$this->refresh = $this->thisCDU["refresh"];
			$this->url = $this->thisCDU["url"];
			$this->xsl = $this->thisCDU["xsl"];
			
			if ($this->thisCDU["notification"] == NULL) {
				$this->notice = 'undefined';
			} else {
				$this->notice = $this->thisCDU["notification"];
			}

		} else {
			$this->CDUsite = '';
		}
		
		$iniValues = parse_ini_file(dirname(dirname(__FILE__)) . DIRECTORY_SEPARATOR . 'controller' . DIRECTORY_SEPARATOR . OPS_INI, FALSE, INI_SCANNER_RAW);
		$this->xhibitLocation = $iniValues[XHIBIT_LOCATION];
		
		$this->xhibitUrl = $iniValues[XHIBIT_URL] . $this->url;

		$proxyUrl = $iniValues[PROXY_LOCATION];
		$this->proxyHttpUrl = $proxyUrl . "?macAddr=" . urlencode($this->macAddress);
		
		$cduUrl = $iniValues[CDU_LOCATION];
		$this->cduHttpUrl = $cduUrl . "?macAddr=" . urlencode($this->macAddress);
	}
	
	private function endsWith($haystack, $needle) {
		// search forward starting from end minus needle length characters
		return $needle === "" || (($temp = strlen($haystack) - strlen($needle)) >= 0 && stripos($haystack, $needle, $temp) !== FALSE);
	}
	
	// this method reads the list of HTML files from local directory
	//  stores as private list.
	// Assume the xhibit folder is in the same parent directory as the manager called "xhibit"
	private function getListofHTMLfiles() {
		$this->htmlList = array();
		
		if ($handle = opendir($this->xhibitLocation)) {
			while (false !== ($file = readdir($handle))) {
				if (($file != ".") 
				 && ($file != "..")
				 && ($this->endswith($file, 'html'))) {
					array_push($this->htmlList, trim($file));
					//print($file);
				}
			}

			closedir($handle);
		}
	}

	//public function display() {}
	function display() {
		//$this->getListofHTMLfiles();
echo <<<START
	<div id="title">
		<!--<img src="images/smartTV_web.jpg">-->
		<a href="index.php">Home</a>
		<h1><i class="fa fa-desktop"></i>
		CDU ($this->CDUsite:$this->CDUindex)</h1>
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
	<script type="text/javascript">
		function changeScreenOption() {
			var helperDropDownCntl = document.getElementById("url-helper");
			var helperTextCntl = document.getElementById("url-helper-text");
			helperTextCntl.innerHTML = helperDropDownCntl.value;
		}
	</script>
  
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
				
				//print_r($this->thisCDU);
				if (!is_null($this->thisCDU)) {
				
					if (!is_null($this->CDUip)) {
					echo <<<CONTROL_REMOTE_CONTROL_PANEL
<section id="remote_control_panel">
	<center>
		<input type="hidden" name="id" value="$this->CDUindex"/>
		<input type="hidden" name="ip" value="$this->CDUip"/>
		<table>
			<tr>
				<td align="center"><a target="_blank" href="cduScreenshot.php?ip=$this->CDUip"><i class="fa fa-desktop"></i><br/>Screenshot</a></td>
			</tr>
			<tr>
				<td colspan="2">&nbsp;</td>
			</tr>
			<tr>
				<td colspan="2">
					<a href="$this->xhibitUrl" target="_blank">$this->url</a><br/>
					<a href="$this->proxyHttpUrl" target="_blank">$this->proxyHttpUrl</a><br/>
					<a href="$this->cduHttpUrl" target="_blank">$this->cduHttpUrl</a><br/>
				</td>
			</tr>
			
		</table>
	</center>
</section>
<br/><br/>
CONTROL_REMOTE_CONTROL_PANEL;
					}
					
					echo <<<NOTIFICATION
<section id="notification">
	<center>
	<form id="notify" name="notify" method="post" action="cdu.php">
		<input type="hidden" name="id" value="$this->CDUindex"/>
		<table class="results">
			<tr><th>Notification</th></tr>
			<tr>
				<td colspan="2" class="results"><textarea name="notification" cols="100" rows="5">$this->notice</textarea></td>
			</tr>
			<tr><td><input type="submit" name="UpdateNotice" value="Update Notice"/></td><td><input type="submit" name="CancelNotice" value="Cancel Notice"/></td></tr>
		</table>
	</form>
	</center>
</section>
NOTIFICATION;

					echo <<<CDU1
<br/><br/>
<section id="CDU">
	<center>
	<form id="cdu" name="cdu" method="post" action="cdu.php">
		<input type="hidden" name="id" value="$this->CDUindex"/>
		<table class="results">
			<tr><th>Title</th><th>Location</th><th colspan=\"2\">Description</th></tr>
			<tr>
				<td class="results"><input type="text" name="title" size="30" maxlength="30" value="$this->title"/></td>
				<td class="results"><input type="text" name="location" size="30" maxlength="50" value="$this->location"/></td>
				<td class="results" colspan="3"><textarea name="description" rows="5" cols="40">$this->description</textarea></td>
			</tr>
			<tr><th>MAC Address</th><th>Screen X</th><th>Screen Y</th><th>Refresh</th><th>XSLt</th></tr>
			<tr>
				<td class="results"><input type="text" name="macAddress" size="17" maxlength="50" value="$this->macAddress"/></td>
				<td class="results">&nbsp;</td>
				<td class="results">&nbsp;</td>
				<td class="results"><input type="text" name="refresh" size="2" maxlength="2" value="$this->refresh"/></td>
				<!--<td class="results"><input type="text" name="xsl" size="15" maxlength="30" value="$this->xsl"/></td-->
					$this->xsl<br/>
				<td class="results">
					<select name="xsl" autocomplete="off">
CDU1;
						if (is_null($this->xsl)) {
							print("<option selected value=\"\">Not Set</option>");
						} else {
							print("<option value=\"\">Not Set</option>");
						}
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
						
				echo <<<CDU2
					</select>
				</td>
			</tr>
			<tr><th colspan="5">URL</th></tr>
			<tr>
				<td colspan="5">
					<input type="text" name="url" size=100 value="$this->url"/><br/>
				</td>
			<tr>
				<td colspan="1">
					<select id="url-helper" name="url-helper"  autocomplete="off" OnChange="changeScreenOption()">
CDU2;
				print("\n");
				//$urlBasename = dirname($this->url);
				$sitePagesValues = $this->controller->getArrayOfSitePagesValues();
				$currentIndex = 0;
				foreach ($this->controller->getArrayOfSitePagesIndexes() as $currentFile) {
					//print("Current row value: ". $sitePagesValues[$currentIndex] . "\n");
					//print("This URL: $this->url\n");
					//$currentURL = $urlBasename . "/" . $currentFile;
					if (strcmp($sitePagesValues[$currentIndex], $this->url) == 0) {
						//print("selected");
						//print("					<option value=\"$currentFile\" selected=\"selected\">$currentFile</option>\n");
						print("					<option value=\"" . $sitePagesValues[$currentIndex] . "\" selected=\"selected\">" . $currentFile . "</option>\n");
					} else {
						//print("not selected");
						print("					<option value=\"" . $sitePagesValues[$currentIndex] . "\" >" . $currentFile . "</option>\n");
					}
					$currentIndex++;
				}
				
				echo <<<CDU3
					</select>
				</td>
				<td colspan="4" align="left">
					<span id="url-helper-text">Select from the dropdown....</span>
				</td>
			</tr>
			<tr><td colspan="5"><input type="submit" name="UpdateCDU" value="Update"/></tr>
		</table>
	</form>
	</center>
</section>
CDU3;



				}
		}
		
echo <<<END
END;
	}

}
?>