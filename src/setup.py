from setuptools import find_packages, setup

setup(
    name='slurpit_netbox',
    version='1.1.8',
    description="Sync Slurp'IT into NetBox",
    install_requires=[
        'requests', 'djangorestframework-bulk'
    ],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)