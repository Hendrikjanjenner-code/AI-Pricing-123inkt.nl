"""
Seed de dim_category_hierarchy tabel vanuit bestaande dim_product data.
Veilig om meerdere keren te draaien — controleert eerst of tabel al gevuld is.
"""
import sys
from database import SessionLocal
import models
from models import DimCategoryHierarchy, DimProduct

db = SessionLocal()

def already_seeded():
    return db.query(DimCategoryHierarchy).count() > 0

def run():
    if already_seeded():
        print("⏭  dim_category_hierarchy al gevuld — overgeslagen")
        db.close()
        return

    # Haal bestaande categorieën + subcategorieën op uit dim_product
    rows = (
        db.query(DimProduct.category, DimProduct.subcategory)
        .filter(DimProduct.category != None)
        .distinct()
        .all()
    )

    # ── Level 1: categorieën ─────────────────────────────────────────────
    cat_names = sorted({r.category for r in rows if r.category})
    cat_id_map: dict[str, int] = {}

    for name in cat_names:
        node = DimCategoryHierarchy(
            category_name=name,
            parent_category_id=None,
            category_level=1,
            active=True,
        )
        db.add(node)
        db.flush()
        cat_id_map[name] = node.category_id
        print(f"  + Categorie: {name} (id={node.category_id})")

    # ── Level 2: subcategorieën ──────────────────────────────────────────
    sub_id_map: dict[tuple, int] = {}  # (cat_name, sub_name) → id

    for row in rows:
        if not row.subcategory:
            continue
        key = (row.category, row.subcategory)
        if key in sub_id_map:
            continue
        parent_id = cat_id_map.get(row.category)
        node = DimCategoryHierarchy(
            category_name=row.subcategory,
            parent_category_id=parent_id,
            category_level=2,
            active=True,
        )
        db.add(node)
        db.flush()
        sub_id_map[key] = node.category_id
        print(f"    + Subcategorie: {row.subcategory} (onder {row.category}, id={node.category_id})")

    # ── Level 3: voorbeelden van sub-subcategorieën ──────────────────────
    # Gebaseerd op de daadwerkelijke productgroepen in de demo-data
    sub_sub_examples = [
        # (parent_cat, parent_sub, sub_sub_name)
        ("Ink & Toner", "Cartridges",           "HP Cartridges"),
        ("Ink & Toner", "Cartridges",           "Canon Cartridges"),
        ("Ink & Toner", "Cartridges",           "Epson Cartridges"),
        ("Ink & Toner", "Cartridges",           "Brother Cartridges"),
        ("Ink & Toner", "Compatible Cartridges","123inkt Compatibel"),
        ("Office Supplies", "Pens & Pencils",   "Balpennen"),
        ("Office Supplies", "Pens & Pencils",   "Potloden"),
        ("Office Supplies", "Pens & Pencils",   "Markers"),
        ("Office Supplies", "Filing & Binders", "Ordners"),
        ("Office Supplies", "Filing & Binders", "Plakband & Tape"),
        ("Paper", "Copy Paper",                 "A4 80 grams"),
        ("Paper", "Copy Paper",                 "A4 90 grams"),
        ("Paper", "Specialty Paper",            "Gekleurd papier"),
        ("Paper", "Specialty Paper",            "Fotopapier"),
        ("Packaging", "Bubble Wrap",            "Klein formaat"),
        ("Packaging", "Bubble Wrap",            "Groot formaat"),
        ("Packaging", "Cardboard Boxes",        "Verzenddozen klein"),
        ("Packaging", "Cardboard Boxes",        "Verzenddozen groot"),
        ("Cleaning", "Floor Cleaning",          "Moppen & Stelen"),
        ("Cleaning", "Floor Cleaning",          "Schrobmachines"),
        ("Cleaning", "Surface Cleaners",        "Allesreinigers"),
        ("Cleaning", "Surface Cleaners",        "Desinfectiemiddelen"),
        ("Canteen Supplies", "Coffee & Tea",    "Koffiepads"),
        ("Canteen Supplies", "Coffee & Tea",    "Theesoorten"),
        ("Canteen Supplies", "Cups & Disposables", "Kartonnen bekers"),
        ("Electronics", "Cables & Adapters",   "USB-kabels"),
        ("Electronics", "Cables & Adapters",   "HDMI-kabels"),
        ("Electronics", "Storage & USB",       "USB-sticks"),
        ("Electronics", "Storage & USB",       "Externe SSD"),
        ("Furniture", "Office Chairs",         "Bureaustoel ergonomisch"),
        ("Furniture", "Office Chairs",         "Bezoekersstoelen"),
        ("Furniture", "Desks",                 "Zit-sta bureaus"),
        ("Furniture", "Desks",                 "Hoekbureaus"),
        ("Printers", "Laser Printers",         "Zwart-wit laser"),
        ("Printers", "Laser Printers",         "Kleurenlaser"),
        ("Printers", "Inkjet Printers",        "Inkjet foto"),
        ("Printers", "Inkjet Printers",        "Inkjet multifunctioneel"),
    ]

    for (cat, sub, subsub) in sub_sub_examples:
        parent_id = sub_id_map.get((cat, sub))
        if parent_id is None:
            continue
        node = DimCategoryHierarchy(
            category_name=subsub,
            parent_category_id=parent_id,
            category_level=3,
            active=True,
        )
        db.add(node)
        db.flush()
        print(f"      + Sub-subcategorie: {subsub} (onder {sub}, id={node.category_id})")

    db.commit()
    total = db.query(DimCategoryHierarchy).count()
    print(f"\n✅ dim_category_hierarchy: {total} records aangemaakt")
    db.close()

if __name__ == "__main__":
    print("🚀 Seed categorie-hiërarchie…")
    run()
    print("🎉 Klaar!")
