<!DOCTYPE HTML>
<!--
	The Rams Head Inn
	html5up.net | @n33co
	Free for personal and commercial use under the CCA 3.0 license (html5up.net/license)
-->
<html>
<head>
	<title>XHIBIT Display Manager &copy; - SITE</title>
	<meta charset="utf-8" />
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
	<meta name="description" content="XHIBIT Display Manager application - &copy; Site"/>
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
	<link rel="stylesheet" href="css/main.css" />
	<link rel="stylesheet" href="css/font-awesome.css" />
</head>
<body>

<?php	
require_once "controller/managerController.php";
require_once "view/managerSiteView.php";

$myController = new ManagerController();
$myController->action("SITE");

$myView = new ManagerSiteView($myController);
$myView->display();
?>
	
</body>
</table>