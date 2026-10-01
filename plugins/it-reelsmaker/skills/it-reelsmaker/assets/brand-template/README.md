# Brand template

This folder is the template for a brand profile: `brand.json` (the profile), `rules.md` (design rules in words) and `assets/` (logos, LUTs, fonts).

To add a new brand:
- copy this folder to `<PROJECT_ROOT>/brands/<slug>/` and fill it in;
- or tell the agent “new brand — name, colors #…, #…, logo file”: it assigns the colors to roles, checks contrast, fills in fonts that cover the brand's language, copies the files into `assets/` and creates `rules.md`.

Real brand folders live in your own project and are never committed to the plugin: they hold the logos, contacts and rules of specific clients.

Details: [`references/brands.md`](../../references/brands.md).
