# pywikibot-scripts
Own pywikibot scripts (for Wikimedia projects)

## Requirements
Python 2.7 (full support not guaranteed) or 3.3.
Pywikibot version [5185a4](https://github.com/wikimedia/pywikibot/tree/5185a4db9c69020ec77908f0b0fae0b453262c53).

## Usage
Checkout or download to "myscripts" directory inside "core/scripts/userscripts".
Then add to your `user-config.py`:
```
user_script_paths = ['scripts.userscripts.myscripts']
```