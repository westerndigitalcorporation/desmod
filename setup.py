# encoding: utf-8
from setuptools import setup

import desmod


setup(
    name='desmod',
    version=desmod.__version__,
    author='Peter Grayson',
    author_email='jpgrayson@gmail.com',
    description='Discrete Event Simulation Modeling using SimPy',
    long_description='\n\n'.join(
        open(f, 'rb').read().decode('utf-8')
        for f in ['README.rst', 'LICENSE.txt']),
    # url='https://',
    # download_url='https://',
    license='MIT',
    install_requires=['simpy', 'six'],
    packages=['desmod'],
    include_package_data=True,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Scientific/Engineering',
    ],
)
