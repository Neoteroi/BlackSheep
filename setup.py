from setuptools import setup, Extension
from blacksheep import __version__


def readme():
    with open('README.md') as f:
        return f.read()


setup(name='blacksheep',
      version=__version__,
      description='Fast HTTP Server/Client microframework for Python asyncio',
      long_description=readme(),
      long_description_content_type='text/markdown',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3.7',
          'Operating System :: OS Independent',
          'Framework :: AsyncIO'
      ],
      url='https://github.com/RobertoPrevato/BlackSheep',
      author='Roberto Prevato',
      author_email='roberto.prevato@gmail.com',
      keywords='BlackSheep web framework',
      platforms=['*nix'],
      license='MIT',
      packages=['blacksheep',
                'blacksheep.server',
                'blacksheep.server.files',
                'blacksheep.server.res'],
      ext_modules=[
          Extension('blacksheep.exceptions',
                    ['blacksheep/exceptions.c'],
                    extra_compile_args=['-O2']),
            
          Extension('blacksheep.headers',
                    ['blacksheep/headers.c'],
                    extra_compile_args=['-O2']),

          Extension('blacksheep.cookies',
                    ['blacksheep/cookies.c'],
                    extra_compile_args=['-O2']),

          Extension('blacksheep.contents',
                    ['blacksheep/contents.c'],
                    extra_compile_args=['-O2']),

          Extension('blacksheep.messages',
                    ['blacksheep/messages.c'],
                    extra_compile_args=['-O2']),

          Extension('blacksheep.scribe',
                    ['blacksheep/scribe.c'],
                    extra_compile_args=['-O2']),

          Extension('blacksheep.connection',
                    ['blacksheep/connection.c'],
                    extra_compile_args=['-O2'])
      ],
      install_requires=[
          'httptools',
          'uvloop'
      ],
      include_package_data=True,
      zip_safe=False)
