<?php
class CDU {
	public $id;
	public $title;
	public $description;
	public $location;
	public $url;
	public $notification;
	public $screenX;
	public $screenY;
	public $refresh;

	function __construct() {
		$this->id = NULL;
		$this->title = NULL;
		$this->description = NULL;
		$this->location = NULL;
		$this->url = NULL;
		$this->notification = NULL;
		$this->screenX = NULL;
		$this->screenY = NULL;
		$this->refresh = NULL;
	}
}

?>