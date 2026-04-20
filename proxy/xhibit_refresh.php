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

if (isset($_GET[HTTP_MAC])) {
	// MAC Address must be in the format: '[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}'
	if (preg_match('/^[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}:[A-Fa-f0-9]{2}$/', $_GET[HTTP_MAC])) {
		$macAddress = $_GET[HTTP_MAC];
	} else {
		exit(1);
	}
	
	$systemCmd = $parserScript . ' ' .escapeshellarg($macAddress) . ' ' . escapeshellarg($dbIniFile) . ' "1"';
	//print ("System Cmd: $systemCmd");
	
	// force response type to XML
	header('Content-type: application/xml');
	system($systemCmd);
	//print ($systemCmd);
	
} else {
	// MAC Address is not given - return an empty response
}
?>
