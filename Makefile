.PHONY: compile release test annotate buildext check-isort check-black


cyt:
	cython blacksheep/url.pyx
	cython blacksheep/exceptions.pyx
	cython blacksheep/headers.pyx
	cython blacksheep/cookies.pyx
	cython blacksheep/contents.pyx
	cython blacksheep/messages.pyx
	cython blacksheep/scribe.pyx
	cython blacksheep/baseapp.pyx

compile: cyt
	python3 setup.py build_ext --inplace


clean:
	rm -rf dist/
	rm -rf build/
	rm -f blacksheep/*.c
	rm -f blacksheep/*.so


buildext:
	python3 setup.py build_ext --inplace


annotate:
	cython blacksheep/url.pyx -a
	cython blacksheep/exceptions.pyx -a
	cython blacksheep/headers.pyx -a
	cython blacksheep/cookies.pyx -a
	cython blacksheep/contents.pyx -a
	cython blacksheep/messages.pyx -a
	cython blacksheep/scribe.pyx -a
	cython blacksheep/baseapp.pyx -a


build: test
	python -m build


prepforbuild:
	pip install --upgrade build


testrelease:
	twine upload -r testpypi dist/*


release: clean compile artifacts
	twine upload -r pypi dist/*


test:
	pytest tests/


itest:
	pytest itests/


init:
	pip install -r requirements.txt


test-v:
	pytest -v


test-cov-unit:
	pytest --cov-report html --cov=blacksheep tests


test-cov:
	pytest --cov-report html --cov=blacksheep --disable-warnings


lint: check-flake8 check-isort check-black

format:
	@isort blacksheep 2>&1
	@isort tests 2>&1
	@isort itests 2>&1
	@black blacksheep 2>&1
	@black tests 2>&1
	@black itests 2>&1

check-flake8:
	@echo "$(BOLD)Checking flake8$(RESET)"
	@flake8 blacksheep 2>&1
	@flake8 tests 2>&1


check-isort:
	@echo "$(BOLD)Checking isort$(RESET)"
	@isort --check-only blacksheep 2>&1
	@isort --check-only tests 2>&1
	@isort --check-only itests 2>&1


check-black:  ## Run the black tool in check mode only (won't modify files)
	@echo "$(BOLD)Checking black$(RESET)"
	@black --check blacksheep 2>&1
	@black --check tests 2>&1
	@black --check itests 2>&1
