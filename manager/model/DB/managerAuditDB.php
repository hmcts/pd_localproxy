<?php
/*
 * managerAuditDB.php
 * 
 * This is the database model for Manager Alert table.
 *
 * Uses PHP:PDO.
 *
 * To handle differences in dialect between database vendors, all SQL defaults to
 *  managerAuditDB-sql.php include (MySQL), but can be overwritten (redefined) with the import of
 *  dialect specific SQL.
 */
define("DB_TYPE_MYSQL", "mysql");
define("DB_TYPE_ORACLE", "oracle");

class ManagerAUDIT_DB {
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
		include("managerAuditDB-sql.php");

		// now import any specific dialects
		switch ($this->dbType) {
			case DB_TYPE_MYSQL:
				//include("managerAuditDB-mysql.php");
				break;
			case DB_TYPE_ORACLE:
				include("managerAuditDB-oracle.php");
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
	
	// this method adds an audit record - returns TRUE or (FALSE on error)
	function newAudit($username, $eventType, $eventData) {
		$status = FALSE;
		try {
			// first, open a connection to the database if not already existing
			if (is_null($this->_dbconn)) {
				$this->open();
			}
			
			// check for errors
			if ($this->isErr()) return $this->strProgress;
			
			// no errors so update data
			array_push($this->strProgress, "Creating AUDIT record for user ($username) with event type ($eventType).");
			$statement = $this->_dbconn->prepare($this->dbSQL[INSERT_SQL]);
			$count = $statement->execute(array('username' => $username,
											   'eventType' => $eventType,
											   'eventData' => $eventData));
			if ($count > 0) {
				array_push($this->strProgress, "Create audit records for ($username).");
				$status = TRUE;
			} else {
				$this->strErr = "Failed to create AUDIT record for ($username).";
			}
			
			return $status;
			
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
