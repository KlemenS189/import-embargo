# Import embargo - check your cross app imports

WARNING: This is stil a WIP project. Contributors welcome.

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

## Limits

- Only imports with absolute paths can be checked.

## Usage:

Output of --help

```
usage: main.py [-h] [--app-root APP_ROOT] [filenames ...]

positional arguments:
  filenames            List of files or directories. Example: src/module_a src/module_b

options:
  -h, --help           show this help message and exit
  --app-root APP_ROOT  Defines the root directory where your python application lives. Must be relative to the cwd path of execution of this script. Default value is current working directory. Example: --app-root=src_folder
```

### Config file

Create a config file called `__embargo__.json` in any module in your python app.
Example config:

```json
{
  "allowed_export_modules": ["your_module_x.submodule"],
  "allowed_import_modules": ["your_submodule_y"],
  "bypass_export_check_for_modules": []
}
```

#### `allowed_export_modules`

Module definitions in the key `allowed_export_modules` mean which modules can be exported and imported from other modules in you app.

#### `allowed_import_modules`

Module definitions in the key `allowed_import_modules` mean which modules can be imported from the checked module.

#### `bypass_export_check_for_modules`

Module definition in the key `bypass_export_check_for_modules` mean which modules can bypass the export check.

If any key is an empty list, nothing is allowed. If the key is missing, check for import/export will be skipped.

### Example directory

```
python_app_root/
├─ payments/
│  ├─ __init__.py
│  ├─ payment_service.py
│  ├─ private_utils.py
│  ├─ __embargo__.json
│  ├─ bank/
│  │  ├─ __init__.py
│  │  ├─ private_banking_services.py/
│  ├─ credit_cards/
│  │  ├─ __init__.py
│  │  ├─ private_credit_card_services.py/
├─ users/
│  ├─ __init__.py
│  ├─ users_service.py
│  ├─ private_service.py
├─ orders/
│  ├─ __init__.py
│  ├─ orders_service.py
│  ├─ __embargo__.json
├─ __init__.py

```

Team who is working on payments doesn't want other teams to access `private_utils` or `private_banking_services.py` directly.
They must go through payment_service. With `payment-embargo`, payments team can create the config `python_app_root/payments/__embargo__.json` with the following contents:

```json
{
  "allowed_export_modules": ["payments.payment_service.py"]
}
```

This will allow `payments.payment_service.py` to be imported in any module, but it will fail for anything else in `payments` module.

Example error when someone from `orders/orders_service.py` would try to import something from `payments/private_utils.py`:

```
 ❌ Export violations detected

/home/user/python_app_root/orders/orders_service.py: payments.private_utils
Allowed exports: [payments.payment_service]
Config file: /home/user/python_app_root/orders/__embargo__.json
```

#### Importing inside of a module

With the example config above, you would limit the exporting to `payments.payment_service.py`. But in the case where `payments.payment_service.py` would import and call some function or method from `payments.bank.private_banking_services`, the export check would fail, because `payments.bank.private_banking_services` is not exported.

To bypass inter module importing, you can use the config key `bypass_export_check_for_modules`.

```json
{
  "allowed_export_modules": ["payments.payment_service.py"],
  "bypass_export_check_for_modules": ["payments"]
}
```

With this config, any inter imports (`payments.payment_service` importing `payments.bank.private_banking_services`) are allowed.

#### Config hierarchy

If something is being imported, `import-embargo` is going to check for `__embargo__.json` on the level of imported module. If config does not exist, it will be searched for in upper directory levels all until the specified python application root.

This feature allows you to create an `__embargo__.json` file on one level and all subdirectories will automatically be protected.

In other words. When searching for config file, the first found config file will be used for checking.

#### Will all of my imports fail if I start using `import-embargo` tool?

No. You can add `__embargo__.json` files incrementaly. If config file does not exist, all of the checks will be skipped.
