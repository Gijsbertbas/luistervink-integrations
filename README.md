# Luistervink Integrations
General integration solutions for Luistervink

## Birdnet-go 
Install the Luistervink task checker for birdnet-go with
```bash
curl -s https://raw.githubusercontent.com/gijsbertbas/luistervink-integrations/main/install.sh | bash
```

Inspect the last 20 log messages from task executions on the device with `sudo journalctl -t luistervink_task_check -n 20` (add `-f` to see live logging).
