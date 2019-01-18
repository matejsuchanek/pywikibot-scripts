# pywikibot-scripts
Own pywikibot scripts (for Wikimedia projects)

## Requirements
Python 2.7 (full support not guaranteed) or 3.3.
Pywikibot version [8a4357](https://github.com/wikimedia/pywikibot/tree/8a4357987620d090f099b145a7fbf99806d1e05b).

## Usage
Checkout or download to "myscripts" directory inside "core/scripts/userscripts".
Then add to your `user-config.py`:
```
user_script_paths = ['scripts.userscripts.myscripts']
```