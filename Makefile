.PHONY: compile release test annotate buildext


cyt:
	cython blacksheep/url.pyx
	cython blacksheep/exceptions.pyx
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
	cython blacksheep/cookies.pyx -a
	cython blacksheep/contents.pyx -a
	cython blacksheep/messages.pyx -a
	cython blacksheep/scribe.pyx -a
	cython blacksheep/baseapp.pyx -a


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
