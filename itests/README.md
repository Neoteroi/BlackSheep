# Integration tests

If tests fail because servers fail to start, try starting them manually:

```bash
# from the root of the repository
export PYTHONPATH="."
export APP_DEFAULT_ROUTER=false
python itests/app_1.py
```
