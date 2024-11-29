import os
from setuptools import setup, find_packages

setup(
    name='ladas2tei',
    version='1.0.0',
    description='A tool to transform ALTO into TEI.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Juliette Janes',
    author_email='juliette.janes@inria.fr',
    url='https://github.com/DEFI-COLaF/LADAS2TEI',
    license='MIT',  # Adjust as needed
    packages=['ladas2tei'],
    include_package_data = True,
    install_requires=[
        # List dependencies here, or use `requirements.txt`
    ],
    entry_points={
        'console_scripts': [
            'ladas2tei=ladas2tei.main:main',  # Command-line interface
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.7',  # Adjust based on compatibility
)
