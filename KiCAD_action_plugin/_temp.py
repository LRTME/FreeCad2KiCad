def startUpdater(self, diff):
    """ old implementation (two part sending to avoid sync drop - this will not be needed anymore with new protocol)"""
    try:
        self.console_logger.log(logging.INFO, f"Diff received: {event.diff}")
        logger.info(f"Diff received: {event.diff}")

        if diff and self.brd and self.pcb:
            self.console_logger.log(logging.INFO, f"[UPDATER] Starting...")
            # Attach diff to as class attribute
            self.diff = diff

            # Call update scripts to apply diff to pcbnew.BOARD
            if self.diff.get("footprints"):
                logger.debug(f"calling update footprints")
                PcbUpdater.updateFootprints(self.brd, self.pcb, self.diff)

            drawings = self.diff.get("drawings")
            changed = None
            added = None
            # Check if NoneType
            if drawings:
                changed = drawings.get("changed")
                added = drawings.get("added")
            # Check if NoneType
            if changed:
                # Update footprints with pcbnew
                PcbUpdater.updateDrawings(self.brd, self.pcb, changed)

            # Check if NoneType
            if added:
                # Don't add new drawings with pcbnew: only update data model. Drawings will be added to pcb after
                # data model sync is confirmed. This is because new drawings (added in FC) have invalid KIID
                # (KIID cannot be set, it's attached to object after instantiation with pcbnew).
                # After data model sync, drawings with invalid KIID are marked as deleted, drawings are added to pcb
                # with new kiid, Differ is called to recognise them as added, Diff is sent to FC where invalid
                # drawings are redrawn and replaced in data model with valid KIIDs
                for drawing in added:
                    # Append drawing with invalid ID to data model to keep data models same
                    logger.debug(f"Adding to data model: {drawing}")
                    self.pcb.get("drawings").append(drawing)
                    logger.debug(f"Data model: {self.pcb}")

            # Send hash of updated data model to freecad, so that FC checks if all diffs were applied
            # correctly
            self.sendHashOfDataModel()

            self.console_logger.log(logging.INFO, f"[UPDATER] Done, refreshing document")
            # Refresh document
            pcbnew.Refresh()

            self.console_logger.log(logging.INFO, f"Clearing local Diff")
            logger.info(f"Clearing local Diff: {self.diff}")
            self.diff = {}
            Plugin.dumpToJsonFile(self.pcb, "/Logs/data_indent.json")

            if added:
                self.addNewDrawingsAndAssingKiid(added)

    except Exception as e:
        logger.exception(e)


def addNewDrawingsAndAssingKiid(self, added):
    # After data model sync, new drawings from FC must be added to pcb with pcbnew
    if added:
        # List of dictionary data
        drawings_updated = []
        # List if KIIDs
        drawings_to_remove = []
        for drawing in added:
            # Draw the new drawings with pcbnew
            valid_kiid = PcbUpdater.addDrawing(brd=self.brd, drawing=drawing)
            # Make a new instance of dictionary, so that drawing stays the same
            drawing_updated = drawing.copy()
            # Override "new-drawing-added-in-freecad" with actual m_Uuid
            drawing_updated.update({"kiid": valid_kiid})
            # Append to list. This will be added to Diff as "added" drawings
            drawings_updated.append(drawing_updated)
            # Append KIID of deleted drawing to list. This will be added to Diff as "removed" drawings
            drawings_to_remove.append(drawing["kiid"])
            # Remove entry with invalid ID from data model
            self.pcb.get("drawings").remove(drawing)
            # Add entry with updated kiid to data model
            self.pcb.get("drawings").append(drawing_updated)

        # Build Diff dictionary as follows:
        #   {
        #       "removed": [drawings with invalid ID, as sent by FreeCAD] <-  to be deleted from sketch and pcb
        #       "added": [KIIDs of newly added drawings] <- to be redrawn in sketch and added to pcb
        #   }
        PcbScanner.updateDiffDict(key="drawings",
                                  value={
                                      "removed": drawings_to_remove,
                                      "added": drawings_updated},
                                  diff=self.diff)

        # Save data model and diff to file for debugging
        Plugin.dumpToJsonFile(self.pcb, "/Logs/data_indent.json")
        Plugin.dumpToJsonFile(self.diff, "/Logs/diff.json")
        # Send diff to FC:
        #   {deleted: [drawings with invalid ID]
        #   added: [newly added drawings to pcb with valid kiid]}
        self.console_logger.log(logging.INFO, "Sending Diff")
        logger.debug("Sending Diff")
        self.sendMessage(json.dumps(self.diff), msg_type="DIF")

        # Refresh document
        pcbnew.Refresh()
