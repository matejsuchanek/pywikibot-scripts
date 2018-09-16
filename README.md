# pywikibot-scripts
Own pywikibot scripts (for Wikimedia projects)

## Requirements
Python 2.7 (full support not guaranteed) or 3.3.
Pywikibot version [ee0a03](https://github.com/wikimedia/pywikibot/tree/ee0a03cef65647ffbf92a91f4d1e5b20fe323ec4).

## Usage
Checkout or download to "myscripts" directory inside "core/scripts/userscripts".
Then add to your `user-config.py`:
```
user_script_paths = ['scripts.userscripts.myscripts']
```