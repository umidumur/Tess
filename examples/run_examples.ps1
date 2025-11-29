# Example PowerShell commands to run scripts (Windows PowerShell / pwsh)

# Set env variables for current session (or create a .env file and the scripts will load it)
$env:API_ID = "123456"
$env:API_HASH = "your_api_hash"

# Change bio
python .\scripts\change_bio.py --about "Automated bio by Tess"

# Send message
python .\scripts\send_message.py --entity "@someuser" --message "Hello from Telethon"

# Auto-reply
python .\scripts\auto_reply.py --phrase "code-phrase" --reply "Auto-reply: Received"
