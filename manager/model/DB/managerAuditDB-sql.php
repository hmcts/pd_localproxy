<?php
/*
 * managerSiteDB-sql.php
 * 
 */
 
$this->dbSQL[INSERT_SQL] = "INSERT INTO `AUDIT` (username, eventType, eventData) values (:username, :eventType, :eventData);";
?>