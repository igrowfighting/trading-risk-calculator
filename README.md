# Trading Risk Calculator

A dark desktop desk-tool for **position size and risk planning**. Enter your ticker, side (long/short), entry price(s), stop, and max dollar risk — get whole-share sizes that **never exceed** your risk cap.

No live market data. No network required to use the app.

## What it does

- **Long / Short** modes with clear green / red styling
- **Single entry** or **scale-in levels** (multiple planned entries)
- Soft default weights heavier near the stop (~20 / 30 / 50 for 3 levels; adjustable sliders)
- Optional **target** P&amp;L and **exit peels** (full dump or partial %)
- **Gap preview** — estimate loss if price gaps through your stop
- **Saved plans** per ticker (stored on your PC)

## Install &amp; run (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) and check **“Add Python to PATH”**.
2. Double-click **`run.bat`**  
   (first run creates a virtual environment and installs dependencies).
3. Or in a terminal from this folder:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python app.py
```

## Build a Windows .exe

On a **Windows** PC (not Linux/Mac):

1. Double-click **`build_windows.bat`**
2. When it finishes, open  
   `dist\TradingRiskCalculator\TradingRiskCalculator.exe`

> PyInstaller builds a Windows executable only when run on Windows. Packaging from Linux cannot produce a native `.exe` without a Windows cross-build setup.

## Install &amp; run (Linux / Mac — for development)

```bash
cd trading-risk-calculator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
# Needs a display + tkinter (e.g. sudo apt install python3-tk)
python app.py
```

Run tests:

```bash
pytest -q
```

## How to use (quick)

1. Choose **Long** or **Short**.
2. Enter **Stop $** and **Max Risk $** (required before share size appears).
3. Enter at least one **entry** price.  
   - Long: entries must be **above** the stop.  
   - Short: entries must be **below** the stop.
4. Optionally **Add Level** for scale-ins; drag weight sliders (they should total ~100%).
5. Optional **Target**, **Exit** price(s), and **Gap-through** price.
6. **Save Plan** stores one plan per ticker (overwrites the previous plan for that symbol).

### Where plans are saved

| OS | Location |
|----|----------|
| Windows | `%APPDATA%\trading-risk-calculator\plans.json` |
| Linux / Mac | `~/.trading-risk-calculator/plans.json` |

## Sizing rules

- **Whole shares only**
- Risk used is always **≤ max risk**. If one more share would push you over (e.g. $301 on a $300 cap), the app uses the largest whole-share count that still fits.

## Project layout

```
app.py                          # launcher
src/trading_risk_calculator/
  sizing.py                     # pure math (tested)
  storage.py                    # saved plans JSON
  app.py                        # UI
  theme.py                      # colors
tests/                          # pytest
run.bat / build_windows.bat
requirements.txt
```

## License

Use freely for personal trading tools. Not financial advice — size and risk are your responsibility.
