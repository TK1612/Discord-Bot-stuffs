# SaintBot-Global-Update-in-Discord
File Sync Bot (Discord to Pixeldrain & Google Sheets)

A Discord bot that scans a local directory, uploads files to Pixeldrain via their REST API, and automatically logs the generated links to a specific column in a Google Sheet. It uses fuzzy matching to find the correct row in your sheet based on the file name. For TT if he wants to study it, i will just throw in the web.

## Features
* `!upload <filename>`: Uploads a specific file and updates the Google Sheet.
* `!uploadfolder <foldername>`: Force uploads an entire folder.
* `!scan <foldername>`: Scans a folder against a local JSON tracking file and only uploads files that are new.

## Setup Instructions

1. **Install Requirements:**
   ```bash
   pip install -r requirements.txt
2. Put in all the necessary infos
3. Run the bot

![649178036_950205537550061_276526426078080711_n](https://github.com/user-attachments/assets/6f7abce4-5bd4-434f-8828-5a20f86740b7)
