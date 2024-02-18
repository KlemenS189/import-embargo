# Import embargo - check your cross app imports

Import embargo is a tool for python applications which can check the imports across your local
packages/modules.

## Why would I need this?

In python there is no enforced encapsulation with public/private by the python interpreter. Anyone can import anything.
This can lead to a mess in medium/large scale applications.

If you strive for **Domain Driven Development**, this package can mark your packages public/private and check for imports which violate the encapsulation.

## Features:

- Define which packages/modules can be imported from your module/package.
- Define which packages/modules can be exported from your module/package.
- Supports Python 3.10+
-

## Limits

- Only imports with absolute paths can be checked.
