<?php
/*
 * managerSiteDB.php
 * 
 * This is the database model for Manager Site table.
 *
 * Uses PHP:PDO.
 *
 * To handle differences in dialect between database vendors, all SQL defaults to
 *  visitorsLogDB-SQL.php include (MySQL), but can be overwritten (redefined) with the import of
 *  dialect specific SQL.
 */
define("DB_TYPE_MYSQL", "mysql");
define("DB_TYPE_ORACLE", "oracle");

class ManagerSITE_DB {
	private $dbConnStr;
	private $dbUser;
	private $dbPasswd;
	private $dbType;
	private $dbSQL;			// associative (hash) array of SQL statements
	
	private $strErr;
	private $strProgress;	// an array of string

	private $_dbconn;

	function __construct($dbConn, $dbUser, $dbPasswd, $dbType) {

		$this->strProgress = array();
		$this->strErr = "";
	
		$this->dbConnStr = $dbConn;
		$this->dbUser = $dbUser;
		$this->dbPasswd = $dbPasswd;
		$this->dbType = $dbType;

		// build the associative array of SQL statements
		$this->dbSQL = array();
		include("managerSiteDB-sql.php");

		// now import any specific dialects
		switch ($this->dbType) {
			case DB_TYPE_MYSQL:
				//include("managerSiteDB-mysql.php");
				break;
			case DB_TYPE_ORACLE:
				include("managerSiteDB-oracle.php");
				break;
		}
	}
	
	// this method returns true if error has been set
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
	
	// returns the progress from model
	function sProgress() {
		return $this->strProgress;
	}

	// closes the connection (if open)
	function close() {
		// we're done! close te connection
		$this->_dbconn = null;
		array_push($this->strProgress, "Closed.");
	}

	// this method opens a connection to the database
	private function open() {
		try {
			//print("url: $this->dbConnStr, user: $this->dbUser, passwd: $this->dbPasswd.\n");
			$this->_dbconn = new PDO($this->dbConnStr, $this->dbUser, $this->dbPasswd);

			array_push($this->strProgress, "DB Connected.");
						
		} catch (PDOException $ex) {
			$this->strErr = "PDOException (open): " . $ex->getMessage();
		} catch (Exception $ex) {
			$this->strErr = $ex->getMessage();
		}
	}
	
	// this method fully updates a SITE reference - or FALSE on error
	function fullUpdate($SITEindex, $title, $xsl, $alert, $selectorURL, $pageURL, $powerSaveSchedule) {
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			// no errors so update data
			array_push($this->strProgress, "Updating SITE with index [$SITEindex] with title($title), xsl($xsl) and alert ($alert).");
			$statement = $this->_dbconn->prepare($this->dbSQL[UPDATE_SQL]);
			$count = $statement->execute(array('title' => $title,
											   'xsl' => $xsl,
											   'alert' => $alert,
											   'selectorUrl' => $selectorURL,
											   'pageUrl' => $pageURL,
											   'SITEid' => $SITEindex,
											   'powersaveSchedule' => $powerSaveSchedule));
			if ($count > 0) {
				array_push($this->strProgress, "Full update to SITE with index [$SITEindex].");
			} else {
				$this->strErr = "Failed to update SITE with index [$SITEindex].";
			}
			
			return $this->strProgress;
			
		} catch (PDOException $ex) {
			$this->strErr = "PDOException (open): " . $ex->getMessage();
			
		} catch (Exception $ex) {
			$this->strErr = $ex->getMessage();
		}
		
		$this->close();
		return FALSE;
	}

	// this method returns a list of SITEs/CDUs.
	//  Values are returns back as an associative array, or FALSE on error
	function fetchAll() {
		$records = array();
		
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			array_push($this->strProgress, "Opened DB.");
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			$statement = $this->_dbconn->prepare($this->dbSQL[SELECT_ALL_SQL]);
			$count = $statement->execute();
			array_push($this->strProgress, "Executed DB.");
			
			$statement->setFetchMode(PDO::FETCH_ASSOC);			
			while ($row = $statement->fetch()) {
				array_push($records, $row);
			}
			//print_r($records);
			//print("fetched " . count($records) . " records");
			array_push($this->strProgress, "Fetched " . count($records) . " records.");
						
			return $records;
			
		} catch (PDOException $ex) {
			$this->strErr = "PDOException (open): " . $ex->getMessage();
			
		} catch (Exception $ex) {
			$this->strErr = $ex->getMessage();
		}
		
		$this->close();
		return FALSE;
	}
	
	// this method returns a single SITE for given index - returns FALSE on error
	function fetch($SITEindex) {
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			$statement = $this->_dbconn->prepare($this->dbSQL[SELECT_SINGLE_SQL]);
			$statement->bindValue(":SITEid", (int) $SITEindex, PDO::PARAM_INT);
			$count = $statement->execute();
			
			// **** DEBUG ****
			//echo $statement->debugDumpParams();

			$statement->setFetchMode(PDO::FETCH_ASSOC);			
			if (FALSE !== $row = $statement->fetch()) {
				//print_r($row);
				//print("fetched " . count($records) . " records");
				array_push($this->strProgress, "Fetched SITE detail having index [$SITEindex].");
						
				return $row;
			} else {
				$this->strErr = "Failed to get SITE details for index [$SITEindex]";
				return FALSE;
			}
			
		} catch (PDOException $ex) {
			$this->strErr = "PDOException (open): " . $ex->getMessage();
			
		} catch (Exception $ex) {
			$this->strErr = $ex->getMessage();
		}
		
		$this->close();
		
		return FALSE;
	}
	
}
?>
