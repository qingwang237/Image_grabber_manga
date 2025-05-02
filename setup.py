import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

setup(
    name="w-grabber",
    version="1.0.0",
    description="Download the manga on wxxx",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/qingwang237/Image_grabber_manga",
    author="Qing Wang",
    author_email="qwqwqw@gmail.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    packages=["wgrabber"],
    include_package_data=True,
    install_requires=[
        "beautifulsoup4==4.5.3",
        "requests==2.32.2",
        "lxml==4.9.1",
        "Click==7.1.2",
        "Pillow==10.3.0",
    ],
    setup_requires=['pytest-runner', 'flake8', 'pylint', 'black'],
    tests_require=[
        'pytest', 'coverage', 'pytest-cov'
    ],
    entry_points={"console_scripts": ["wgrabber=wgrabber.__main__:main",]},
)
