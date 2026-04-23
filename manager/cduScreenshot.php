<?php

// extract the IP Address from the HTTP parameters 
$ipAddress = NULL;
if (isset($_GET["ip"])) {
	$ipAddress = $_GET["ip"];
}

// call upon the CDU to return the screenshot
$httpUrl = "http://$ipAddress:8080/screenshot.php";
$ctx = stream_context_create(array('http' => array('timeout' => 10, 'method' => "GET")));
$xmlStr = file_get_contents($httpUrl, false, $ctx);

if ($xmlStr !== FALSE) {
	header("Content-Type: image/png");
	print($xmlStr);
} else {
?>
<html>
	<body>
		<p>Fetching from: <?php print ($httpUrl);?></p>
	</body>
</html>
<?php
}
?>
