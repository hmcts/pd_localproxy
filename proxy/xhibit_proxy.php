<?php
define("INI_FILE", "proxy.ini");
define("DB_INI_FILE", "DB_INI_FILE");
define("PARSER", "PARSER_SCRIPT");

define("HTTP_MAC", "macAddr");
define("HTTP_CURRENT_PAGE_INDEX", "currentPageIndex");
define("HTTP_DATA_REFRESH", "data_refresh");

$iniValues = parse_ini_file(INI_FILE, FALSE, INI_SCANNER_RAW);
$dbIniFile = $iniValues[DB_INI_FILE];
$parserScript = $iniValues[PARSER];

$currentPageIndex = NULL;
// extract the Current Page Index from the HTTP parameters if it exists
if (isset($_GET[HTTP_CURRENT_PAGE_INDEX])) {
	if (is_int(intval($_GET[HTTP_CURRENT_PAGE_INDEX]))) {
		$currentPageIndex = intval($_GET[HTTP_CURRENT_PAGE_INDEX]);
	}
}

$dataRefresh = NULL;
// extract the Data Refesh from the HTTP parameters if it exists
if (isset($_GET[HTTP_DATA_REFRESH])) {
	if (is_int($_GET[HTTP_DATA_REFRESH])) {
		$dataRefresh = 1;
	}
}

if (isset($_GET[HTTP_MAC])) {
	// MAC Address must be in the format: '[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}'
	if (preg_match('/^[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}$/', $_GET[HTTP_MAC])) {
		$macAddress = $_GET[HTTP_MAC];
	} else {
		exit(1);
	}
	
	if (isset($currentPageIndex)) {
		if (isset($dataRefresh)) {
			$systemCmd = $parserScript . ' ' .escapeshellarg($macAddress) . ' ' . escapeshellarg($dbIniFile) . ' "0" ' . escapeshellarg($currentPageIndex) . ' ' . escapeshellarg($dataRefresh);
		} else {
			$systemCmd = $parserScript . ' ' .escapeshellarg($macAddress) . ' ' . escapeshellarg($dbIniFile) . ' "0" ' . escapeshellarg($currentPageIndex);
		}
	} else {
		$systemCmd = $parserScript . ' ' .escapeshellarg($macAddress) . ' ' . escapeshellarg($dbIniFile) . ' "0"';
	}
	//print ("System Cmd: $systemCmd");
	
	// force response type to XML
	header('Content-type: application/xml');
	system($systemCmd);
	//print ($systemCmd);
	
} else {
	// MAC Address is not given - return an empty response
}
?>
