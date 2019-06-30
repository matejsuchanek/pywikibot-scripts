# pywikibot-scripts
Own pywikibot scripts (for Wikimedia projects)

## Requirements
Python 2.7 (full support not guaranteed) or 3.3.
Pywikibot version [7c22ff](https://github.com/wikimedia/pywikibot/tree/04d86b1f9e973f6e0906298ad2fafb7be3cf18fe).

## Usage
Checkout or download to "myscripts" directory inside "core/scripts/userscripts".
Then add to your `user-config.py`:
```
user_script_paths = ['scripts.userscripts.myscripts']
```