.PHONY: compile release test annotate buildext


cyt:
	cythonize -i blacksheep/url.pyx
	cythonize -i blacksheep/exceptions.pyx
	cythonize -i blacksheep/headers.pyx
	cythonize -i blacksheep/cookies.pyx
	cythonize -i blacksheep/contents.pyx
	cythonize -i blacksheep/messages.pyx
	cythonize -i blacksheep/scribe.pyx
	cythonize -i blacksheep/options.pyx
	cythonize -i blacksheep/baseapp.pyx
	cythonize -i blacksheep/connection.pyx

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
	cython blacksheep/options.pyx -a
	cython blacksheep/baseapp.pyx -a
	cython blacksheep/connection.pyx -a


artifacts: test
	python setup.py sdist


prepforbuild:
	pip install --upgrade twine setuptools wheel


testrelease:
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*


release: clean compile artifacts
	twine upload --repository-url https://upload.pypi.org/legacy/ dist/*


test:
	pytest


init:
	pip install -r requirements.txt


test-v:
	pytest -v
