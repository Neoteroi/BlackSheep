.PHONY: compile release test annotate buildext check-isort check-black


cyt:
	cython neoteroi/web/url.pyx
	cython neoteroi/web/exceptions.pyx
	cython neoteroi/web/headers.pyx
	cython neoteroi/web/cookies.pyx
	cython neoteroi/web/contents.pyx
	cython neoteroi/web/messages.pyx
	cython neoteroi/web/scribe.pyx
	cython neoteroi/web/baseapp.pyx

compile: cyt
	python3 setup.py build_ext --inplace


clean:
	rm -rf dist/
	rm -rf build/
	rm -f neoteroi/web/*.c
	rm -f neoteroi/web/*.so


buildext:
	python3 setup.py build_ext --inplace


annotate:
	cython neoteroi/web/url.pyx -a
	cython neoteroi/web/exceptions.pyx -a
	cython neoteroi/web/headers.pyx -a
	cython neoteroi/web/cookies.pyx -a
	cython neoteroi/web/contents.pyx -a
	cython neoteroi/web/messages.pyx -a
	cython neoteroi/web/scribe.pyx -a
	cython neoteroi/web/baseapp.pyx -a


artifacts: test
	python setup.py sdist


prepforbuild:
	pip install --upgrade twine setuptools wheel


testrelease:
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*


release: clean compile artifacts
	twine upload --repository-url https://upload.pypi.org/legacy/ dist/*


test:
	pytest tests/


itest:
	pytest itests/


init:
	pip install -r requirements.txt


test-v:
	pytest -v


test-cov-unit:
	pytest --cov-report html --cov=neoteroi/web tests


test-cov:
	pytest --cov-report html --cov=neoteroi/web --disable-warnings


lint: check-flake8 check-isort check-black

format:
	@isort neoteroi/web 2>&1
	@isort tests 2>&1
	@isort itests 2>&1
	@black neoteroi/web 2>&1
	@black tests 2>&1
	@black itests 2>&1

check-flake8:
	@echo "$(BOLD)Checking flake8$(RESET)"
	@flake8 neoteroi/web 2>&1
	@flake8 tests 2>&1


check-isort:
	@echo "$(BOLD)Checking isort$(RESET)"
	@isort --check-only neoteroi/web 2>&1
	@isort --check-only tests 2>&1
	@isort --check-only itests 2>&1


check-black:  ## Run the black tool in check mode only (won't modify files)
	@echo "$(BOLD)Checking black$(RESET)"
	@black --check neoteroi/web 2>&1
	@black --check tests 2>&1
	@black --check itests 2>&1
