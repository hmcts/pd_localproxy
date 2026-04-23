<?php
/*
 * managerCDUDB.php
 * 
 * This is the database model for Manager CDU table.
 *
 * Uses PHP:PDO.
 *
 * To handle differences in dialect between database vendors, all SQL defaults to
 *  visitorsLogDB-SQL.php include (MySQL), but can be overwritten (redefined) with the import of
 *  dialect specific SQL.
 */
define("DB_TYPE_MYSQL", "mysql");
define("DB_TYPE_ORACLE", "oracle");

define("CREATE_TABLE_SQL", "UPDATE_SQL");
define("INSERT_SQL", "RESET_NOTIFICATION_UPDATE_SQL");
define("SELECT_LIMIT_SQL", "NOTIFICATION_UPDATE_SQL");
define("SELECT_LIMIT_SQL", "SELECT_ALL_SQL");
define("SELECT_LIMIT_SQL", "SELECT_SINGLE_SQL");
define("SELECT_IPHISTORY_SQL", "SELECT_IPHISTORY_SQL");

class ManagerCDU_DB {
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
		include("managerCDUDB-sql.php");

		// now import any specific dialects
		switch ($this->dbType) {
			case DB_TYPE_MYSQL:
				//include("managerCDUDB-mysql.php");
				break;
			case DB_TYPE_ORACLE:
				include("managerCDUDB-oracle.php");
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
	
	// this method fully updates a CDU reference - or FALSE on error
	function fullUpdate($CDUindex, $macAddress, $title, $description, $location, $url, $xsl, $refresh) {
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			// no errors so update data
			$statement = $this->_dbconn->prepare($this->dbSQL[UPDATE_SQL]);
			$count = $statement->execute(array('macAddress' => $macAddress,
			                                   'title' => $title,
											   'description' => $description,
											   'location' => $location,
											   'url' => $url,
											   'xsl' => $xsl,
											   'refresh' => $refresh,
											   'CDUid' => $CDUindex));
			if ($count > 0) {
				array_push($this->strProgress, "Full update to CDU with index [$CDUindex].");
			} else {
				$this->strErr = "Failed to update CDU with index [$CDUindex].";
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

	// this method sets notification message for a CDU reference. If the "notification" is NULL,
	//  this method resets the notification message.
	// Returns FALSE on error.
	function notificationUpdate($CDUindex, $notification) {
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			// no errors so insert data
			if (is_null($notification)) {
				$statement = $this->_dbconn->prepare($this->dbSQL[RESET_NOTIFICATION_UPDATE_SQL]);
				$statement->bindValue(":CDUid", (int) $CDUindex, PDO::PARAM_INT);
				$count = $statement->execute();
												   
			} else {
				$statement = $this->_dbconn->prepare($this->dbSQL[NOTIFICATION_UPDATE_SQL]);
				//$statement->bindValue(":CDUid", (int) $CDUindex, PDO::PARAM_INT);
				//$statement->bindValue(":notification", (int) $notification, PDO::PARAM_STR);
				$count = $statement->execute(array('CDUid' => $CDUindex,
			                                   'notification' => $notification));
			}
			
			if ($count > 0) {
				array_push($this->strProgress, "Notification updated to CDU with index [$CDUindex].");
			} else {
				$this->strErr = "Failed to update notification to CDU with index [$CDUindex].";
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

	// this method returns a list of CDUs.
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
	
	// this method returns a single CDU for given index - returns FALSE on error
	function fetch($CDUindex) {		
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			$statement = $this->_dbconn->prepare($this->dbSQL[SELECT_SINGLE_SQL]);
			$statement->bindValue(":CDUid", (int) $CDUindex, PDO::PARAM_INT);
			$count = $statement->execute();
			
			// **** DEBUG ****
			//echo $statement->debugDumpParams();

			$statement->setFetchMode(PDO::FETCH_ASSOC);			
			if (FALSE !== $row = $statement->fetch()) {
				//print_r($row);
				//print("fetched " . count($records) . " records");
				array_push($this->strProgress, "Fetched CDU detail having index [$CDUindex].");
						
				return $row;
			} else {
				$this->strErr = "Failed to get CDU details for index [$CDUindex]";
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

	// this method returns a IP History CDU for given index - returns FALSE on error
	function fetchIpHistory($CDUindex, $maxRows) {
		$records = array();
		
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			array_push($this->strProgress, "Opened DB for fetchIpHistory.");
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			//echo "IP History CDU id[$CDUindex] with max rows [$maxRows].";
			$statement = $this->_dbconn->prepare($this->dbSQL[SELECT_IPHISTORY_SQL]);			
			$statement->bindValue(":maximumRows", (int) $maxRows, PDO::PARAM_INT);
			$statement->bindValue(":CDUid", (int) $CDUindex, PDO::PARAM_INT);
			$count = $statement->execute();
			array_push($this->strProgress, "Executed DB.");

			// **** DEBUG ****
			//echo $statement->debugDumpParams();
			
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
	
	// this method returns the selector URL of the associated site for given CDU index - returns FALSE on error
	function fetchSelectorURL($CDUindex) {
		$records = array();
		
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			array_push($this->strProgress, "Opened DB for fetchIpHistory.");
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			//echo "IP History CDU id[$CDUindex] with max rows [$maxRows].";
			$statement = $this->_dbconn->prepare($this->dbSQL[SELECT_SELECTOR_URL]);		
			$statement->bindValue(":CDUid", (int) $CDUindex, PDO::PARAM_INT);
			$count = $statement->execute();
			array_push($this->strProgress, "Executed DB.");

			// **** DEBUG ****
			//echo $statement->debugDumpParams();
			
			$statement->setFetchMode(PDO::FETCH_ASSOC);
			if (FALSE !== $row = $statement->fetch()) {
				//print_r($row);
				//print("fetched " . count($records) . " records");
				$selectorURL = $row["selectorUrl"];
				array_push($this->strProgress, "Fetched Selector URL ($selectorURL) for CDU having index [$CDUindex].");
						
				return $selectorURL;
			} else {
				$this->strErr = "Failed to get SelectorURL for CDU having index [$CDUindex]";
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
