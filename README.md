# pywikibot-scripts
Own pywikibot scripts (for Wikimedia projects)

## Requirements
Python 2.7 (full support not guaranteed) or 3.3.
Pywikibot version [13b243](https://github.com/wikimedia/pywikibot/tree/13b24343607c0e34dcfbe1430b0ea50245fc496a).

## Usage
Checkout or download to "myscripts" directory inside "core/scripts/userscripts".
Then add to your `user-config.py`:
```
user_script_paths = ['scripts.userscripts.myscripts']
```