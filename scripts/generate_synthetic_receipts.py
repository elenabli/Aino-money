#!/usr/bin/env python3
"""Generate deterministic, itemized synthetic Prisma receipts for Aino Money.

The source transactions provide customers, dates, merchants, and exact receipt
Totals. Products, item selection, prices, and nutrition values are synthetic.
Nutrition values describe estimated purchased food, not consumed food or diet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_CUSTOMERS = ("CUST02220", "CUST05013", "CUST00001")
NUTRIENTS = (
    "energy_kcal",
    "protein_g",
    "carbohydrate_g",
    "sugar_g",
    "fat_g",
    "saturated_fat_g",
    "fibre_g",
    "salt_g",
)

PRODUCE = "Fruit & vegetables"
DAIRY = "Dairy & eggs"
PROTEIN = "Meat, fish & plant proteins"
BAKERY = "Bakery & grains"
DRINKS = "Drinks"
SNACKS = "Snacks & sweets"
READY = "Frozen & ready meals"
PANTRY = "Pantry"
HOUSEHOLD = "Household & personal care"


@dataclass(frozen=True)
class Product:
    product_id: str
    name: str
    category: str
    tags: str
    base_price_eur: Decimal
    package_size: Decimal | None
    package_unit: str
    nutrients: dict[str, Decimal] | None
    weighted: bool = False
    nutrition_confidence: Decimal | None = Decimal("0.70")

    @property
    def is_food(self) -> bool:
        return self.nutrients is not None

    @property
    def nutrition_per(self) -> str:
        if not self.is_food:
            return ""
        return "100ml" if self.package_unit == "ml" else "100g"


def food(
    product_id: str,
    name: str,
    category: str,
    tags: str,
    price: str,
    package_size: str,
    package_unit: str,
    values: tuple[str, str, str, str, str, str, str, str],
    *,
    weighted: bool = False,
    confidence: str = "0.70",
) -> Product:
    return Product(
        product_id,
        name,
        category,
        tags,
        Decimal(price),
        Decimal(package_size),
        package_unit,
        dict(zip(NUTRIENTS, (Decimal(v) for v in values))),
        weighted,
        Decimal(confidence),
    )


def household(product_id: str, name: str, price: str) -> Product:
    return Product(
        product_id, name, HOUSEHOLD, "non_food", Decimal(price), None, "", None, False, None
    )


# Fictional generic-product catalogue. Values are plausible synthetic estimates,
# not copied product labels and not assertions about real Prisma assortment.
PRODUCTS = [
    food("P001", "Bananas", PRODUCE, "fruit_vegetable;fresh_produce", "2.35", "1000", "g", ("89", "1.1", "22.8", "12.2", "0.3", "0.1", "2.6", "0"), weighted=True, confidence="0.85"),
    food("P002", "Apples", PRODUCE, "fruit_vegetable;fresh_produce", "3.49", "1000", "g", ("52", "0.3", "13.8", "10.4", "0.2", "0", "2.4", "0"), weighted=True, confidence="0.85"),
    food("P003", "Carrots", PRODUCE, "fruit_vegetable;fresh_produce", "1.79", "1000", "g", ("41", "0.9", "9.6", "4.7", "0.2", "0.1", "2.8", "0.07"), weighted=True, confidence="0.85"),
    food("P004", "Potatoes", PRODUCE, "fruit_vegetable;fresh_produce", "1.49", "1000", "g", ("77", "2", "17.5", "0.8", "0.1", "0", "2.2", "0.01"), weighted=True, confidence="0.85"),
    food("P005", "Tomatoes", PRODUCE, "fruit_vegetable;fresh_produce", "3.99", "1000", "g", ("18", "0.9", "3.9", "2.6", "0.2", "0", "1.2", "0.01"), weighted=True, confidence="0.85"),
    food("P006", "Cucumber 400g", PRODUCE, "fruit_vegetable;fresh_produce", "1.29", "400", "g", ("15", "0.7", "3.6", "1.7", "0.1", "0", "0.5", "0.02"), confidence="0.85"),
    food("P007", "Bell pepper 160g", PRODUCE, "fruit_vegetable;fresh_produce", "1.49", "160", "g", ("31", "1", "6", "4.2", "0.3", "0", "2.1", "0.01"), confidence="0.85"),
    food("P008", "Frozen broccoli 500g", PRODUCE, "fruit_vegetable;frozen_vegetable", "2.79", "500", "g", ("34", "2.8", "6.6", "1.5", "0.4", "0.1", "2.6", "0.03"), confidence="0.80"),
    food("P009", "Frozen berries 400g", PRODUCE, "fruit_vegetable;frozen_fruit", "3.99", "400", "g", ("45", "0.7", "10", "8", "0.3", "0", "3", "0.01"), confidence="0.80"),
    food("P010", "Salad mix 150g", PRODUCE, "fruit_vegetable;fresh_produce", "2.49", "150", "g", ("18", "1.4", "2.8", "1.4", "0.2", "0", "1.6", "0.04"), confidence="0.85"),
    food("P011", "Onions", PRODUCE, "fruit_vegetable;fresh_produce", "1.69", "1000", "g", ("40", "1.1", "9.3", "4.2", "0.1", "0", "1.7", "0.01"), weighted=True, confidence="0.85"),
    food("P012", "Oranges", PRODUCE, "fruit_vegetable;fresh_produce", "3.29", "1000", "g", ("47", "0.9", "11.8", "9.4", "0.1", "0", "2.4", "0"), weighted=True, confidence="0.85"),
    food("P013", "Whole milk 1L", DAIRY, "dairy", "1.19", "1000", "ml", ("64", "3.3", "4.7", "4.7", "3.5", "2.1", "0", "0.1"), confidence="0.80"),
    food("P014", "Semi-skimmed milk 1L", DAIRY, "dairy", "1.09", "1000", "ml", ("47", "3.4", "4.8", "4.8", "1.5", "0.9", "0", "0.1"), confidence="0.80"),
    food("P015", "Oat drink 1L", DAIRY, "plant_based_dairy", "1.89", "1000", "ml", ("46", "1", "6.7", "4", "1.5", "0.2", "0.8", "0.1"), confidence="0.65"),
    food("P016", "Natural skyr 200g", DAIRY, "dairy;protein_source", "1.29", "200", "g", ("63", "11", "4", "4", "0.2", "0.1", "0", "0.12"), confidence="0.70"),
    food("P017", "Natural Greek yoghurt 400g", DAIRY, "dairy;protein_source", "2.49", "400", "g", ("97", "6", "4", "4", "5", "3.5", "0", "0.15"), confidence="0.70"),
    food("P018", "Strawberry yoghurt 400g", DAIRY, "dairy;sweetened_dairy", "1.69", "400", "g", ("92", "3.2", "12.5", "11.5", "2.5", "1.5", "0", "0.12"), confidence="0.65"),
    food("P019", "Hard cheese 400g", DAIRY, "dairy;protein_source", "4.29", "400", "g", ("350", "25", "1", "1", "27", "17", "0", "1.7"), confidence="0.70"),
    food("P020", "Eggs 10-pack 600g", DAIRY, "eggs;protein_source", "2.99", "600", "g", ("143", "12.6", "0.7", "0.7", "9.5", "2.7", "0", "0.35"), confidence="0.80"),
    food("P021", "Unsalted butter 400g", DAIRY, "dairy", "3.49", "400", "g", ("717", "0.8", "0.7", "0.7", "81", "51", "0", "0.02"), confidence="0.80"),
    food("P022", "Natural quark 250g", DAIRY, "dairy;protein_source", "2.29", "250", "g", ("75", "13", "3.5", "3.5", "0.2", "0.1", "0", "0.1"), confidence="0.70"),
    food("P023", "Chicken fillet 600g", PROTEIN, "meat;protein_source", "8.99", "600", "g", ("110", "23", "0", "0", "2.5", "0.7", "0", "0.15"), confidence="0.75"),
    food("P024", "Salmon fillet 400g", PROTEIN, "fish;protein_source", "10.99", "400", "g", ("208", "20", "0", "0", "13", "2.5", "0", "0.15"), confidence="0.75"),
    food("P025", "Ground beef 500g", PROTEIN, "meat;protein_source", "7.49", "500", "g", ("215", "19", "0", "0", "15", "6", "0", "0.2"), confidence="0.75"),
    food("P026", "Smoked ham 200g", PROTEIN, "meat;protein_source;processed_meat", "2.49", "200", "g", ("115", "17", "2", "1.5", "3.5", "1.2", "0", "2.2"), confidence="0.65"),
    food("P027", "Tofu 400g", PROTEIN, "plant_protein;protein_source;vegetarian", "2.79", "400", "g", ("145", "15", "2", "1", "9", "1.3", "2", "0.1"), confidence="0.70"),
    food("P028", "Red lentils 500g", PROTEIN, "plant_protein;protein_source;legume;vegetarian", "2.29", "500", "g", ("350", "24", "60", "2", "1.5", "0.2", "11", "0.02"), confidence="0.85"),
    food("P029", "Chickpeas 240g drained", PROTEIN, "plant_protein;protein_source;legume;vegetarian", "1.19", "240", "g", ("139", "7.2", "22", "1.5", "2.4", "0.3", "6.4", "0.6"), confidence="0.80"),
    food("P030", "Black beans 240g drained", PROTEIN, "plant_protein;protein_source;legume;vegetarian", "1.25", "240", "g", ("114", "7.5", "17", "1", "0.7", "0.1", "7", "0.6"), confidence="0.80"),
    food("P031", "Frozen fish fingers 400g", PROTEIN, "fish;protein_source;ready_meal", "3.49", "400", "g", ("220", "12", "18", "1", "11", "1.5", "1", "0.9"), confidence="0.60"),
    food("P032", "Hummus 200g", PROTEIN, "plant_protein;protein_source;legume;vegetarian", "2.49", "200", "g", ("190", "7", "10", "1", "13", "1.8", "5", "1.2"), confidence="0.65"),
    food("P033", "Rye bread 500g", BAKERY, "bread;whole_grain;high_fibre", "2.49", "500", "g", ("220", "7", "42", "3", "2", "0.4", "10", "1.2"), confidence="0.70"),
    food("P034", "Wholegrain bread 500g", BAKERY, "bread;whole_grain", "2.29", "500", "g", ("235", "9", "41", "4", "3", "0.5", "7", "1.1"), confidence="0.70"),
    food("P035", "White toast 400g", BAKERY, "bread;refined_grain", "1.79", "400", "g", ("265", "8", "49", "5", "3.5", "0.7", "2.8", "1.2"), confidence="0.70"),
    food("P036", "Oat flakes 500g", BAKERY, "breakfast;whole_grain;high_fibre", "1.49", "500", "g", ("370", "13", "60", "1", "7", "1.2", "10", "0.01"), confidence="0.85"),
    food("P037", "Wholegrain pasta 500g", BAKERY, "pasta;whole_grain", "1.39", "500", "g", ("350", "13", "68", "3", "2", "0.4", "8", "0.02"), confidence="0.80"),
    food("P038", "White rice 1kg", BAKERY, "rice;refined_grain", "1.59", "1000", "g", ("360", "7", "80", "0.2", "0.7", "0.2", "1.3", "0.01"), confidence="0.85"),
    food("P039", "Wholegrain rice 1kg", BAKERY, "rice;whole_grain", "1.99", "1000", "g", ("350", "7.5", "76", "1", "2.5", "0.5", "3", "0.01"), confidence="0.85"),
    food("P040", "Tortillas 320g", BAKERY, "bread;refined_grain", "2.19", "320", "g", ("310", "8", "50", "3", "8", "3", "3", "1.5"), confidence="0.65"),
    food("P041", "Sweet breakfast cereal 500g", BAKERY, "breakfast;sweetened_cereal", "3.49", "500", "g", ("380", "8", "78", "22", "4", "0.8", "7", "0.5"), confidence="0.60"),
    food("P042", "No-added-sugar muesli 600g", BAKERY, "breakfast;whole_grain;high_fibre", "3.29", "600", "g", ("375", "10", "62", "14", "8", "1", "9", "0.05"), confidence="0.65"),
    food("P043", "Cola 1.5L", DRINKS, "sweetened_drink;soft_drink", "1.89", "1500", "ml", ("42", "0", "10.6", "10.6", "0", "0", "0", "0.01"), confidence="0.75"),
    food("P044", "Orange juice 1L", DRINKS, "juice;fruit_drink", "2.29", "1000", "ml", ("45", "0.7", "10.4", "9.5", "0.2", "0", "0.2", "0.02"), confidence="0.70"),
    food("P045", "Apple juice 1L", DRINKS, "juice;fruit_drink", "1.89", "1000", "ml", ("46", "0.1", "11.2", "10.5", "0.1", "0", "0.2", "0.02"), confidence="0.70"),
    food("P046", "Sugar-free cola 1.5L", DRINKS, "sugar_free_drink;soft_drink", "1.89", "1500", "ml", ("0.4", "0", "0", "0", "0", "0", "0", "0.02"), confidence="0.75"),
    food("P047", "Energy drink 500ml", DRINKS, "sweetened_drink;energy_drink", "2.49", "500", "ml", ("46", "0", "11", "11", "0", "0", "0", "0.1"), confidence="0.75"),
    food("P048", "Sparkling water 1.5L", DRINKS, "water;unsweetened_drink", "0.89", "1500", "ml", ("0", "0", "0", "0", "0", "0", "0", "0"), confidence="0.90"),
    food("P049", "Chocolate milk 1L", DRINKS, "sweetened_drink;dairy_drink", "2.29", "1000", "ml", ("67", "3.4", "10.5", "10", "2", "1.2", "0", "0.15"), confidence="0.65"),
    food("P050", "Bottled water 1.5L", DRINKS, "water;unsweetened_drink", "0.69", "1500", "ml", ("0", "0", "0", "0", "0", "0", "0", "0"), confidence="0.90"),
    food("P051", "Milk chocolate 200g", SNACKS, "sweets_snacks;chocolate", "2.19", "200", "g", ("535", "7.5", "57", "56", "31", "19", "2", "0.2"), confidence="0.65"),
    food("P052", "Dark chocolate 200g", SNACKS, "sweets_snacks;chocolate", "2.49", "200", "g", ("550", "8", "45", "40", "38", "22", "9", "0.05"), confidence="0.65"),
    food("P053", "Potato crisps 200g", SNACKS, "sweets_snacks;savoury_snack", "2.49", "200", "g", ("510", "6", "52", "3", "29", "3", "4", "1.3"), confidence="0.65"),
    food("P054", "Salted mixed nuts 300g", SNACKS, "savoury_snack;protein_source", "3.49", "300", "g", ("590", "20", "18", "5", "49", "7", "8", "1"), confidence="0.75"),
    food("P055", "Biscuits 300g", SNACKS, "sweets_snacks;biscuits", "1.99", "300", "g", ("480", "6", "65", "32", "20", "9", "2", "0.5"), confidence="0.65"),
    food("P056", "Vanilla ice cream 500g", SNACKS, "sweets_snacks;ice_cream", "3.99", "500", "g", ("205", "3.5", "24", "22", "10", "6", "0", "0.1"), confidence="0.65"),
    food("P057", "Fruit candy 200g", SNACKS, "sweets_snacks;candy", "2.29", "200", "g", ("390", "0.5", "95", "75", "0.5", "0.1", "0", "0.05"), confidence="0.65"),
    food("P058", "Granola bars 180g", SNACKS, "sweets_snacks;cereal_bar", "2.79", "180", "g", ("420", "8", "60", "25", "14", "5", "6", "0.25"), confidence="0.60"),
    food("P059", "Popcorn 150g", SNACKS, "savoury_snack", "1.79", "150", "g", ("430", "9", "55", "1", "18", "3", "10", "1.2"), confidence="0.65"),
    food("P060", "Frozen pizza 400g", READY, "ready_meal;frozen_meal", "3.49", "400", "g", ("250", "10", "30", "4", "9", "4", "2", "1.2"), confidence="0.60"),
    food("P061", "Lasagne ready meal 400g", READY, "ready_meal", "4.29", "400", "g", ("155", "7", "15", "3", "6", "2.5", "1.5", "0.8"), confidence="0.60"),
    food("P062", "Vegetable stir-fry 500g", READY, "fruit_vegetable;frozen_vegetable;vegetarian", "3.29", "500", "g", ("55", "2.5", "7", "4", "1.5", "0.3", "3", "0.4"), confidence="0.65"),
    food("P063", "Tomato soup 400g", READY, "ready_meal;soup", "1.89", "400", "g", ("55", "1.8", "9", "5", "1", "0.2", "1.2", "0.7"), confidence="0.65"),
    food("P064", "Vegetable burgers 300g", READY, "ready_meal;plant_protein;protein_source;vegetarian", "3.99", "300", "g", ("210", "14", "16", "2", "9", "1.2", "6", "1.1"), confidence="0.60"),
    food("P065", "Salmon sushi 300g", READY, "ready_meal;fish;protein_source", "6.99", "300", "g", ("165", "6", "27", "4", "3.5", "0.7", "1.5", "1.1"), confidence="0.55"),
    food("P066", "Peanut butter 350g", PANTRY, "plant_protein;protein_source;legume", "3.29", "350", "g", ("598", "25", "16", "6", "50", "9", "7", "0.4"), confidence="0.70"),
    food("P067", "Olive oil 500ml", PANTRY, "cooking_oil", "5.99", "500", "ml", ("824", "0", "0", "0", "91.6", "14", "0", "0"), confidence="0.85"),
    food("P068", "Tomato passata 400g", PANTRY, "cooking_ingredient;fruit_vegetable", "1.29", "400", "g", ("35", "1.5", "6", "4.5", "0.2", "0", "1.5", "0.15"), confidence="0.75"),
    food("P069", "Basil pesto 190g", PANTRY, "cooking_ingredient", "2.99", "190", "g", ("360", "5", "8", "3", "34", "6", "2", "1.5"), confidence="0.60"),
    food("P070", "Tuna in water 160g drained", PANTRY, "fish;protein_source", "1.79", "160", "g", ("105", "24", "0", "0", "1", "0.3", "0", "0.8"), confidence="0.75"),
    household("P071", "Paper towels 2 rolls", "2.49"),
    household("P072", "Toilet paper 8 rolls", "4.99"),
    household("P073", "Dish soap 500ml", "1.89"),
    household("P074", "Laundry detergent 1L", "6.99"),
    household("P075", "Toothpaste 75ml", "2.29"),
    household("P076", "Shampoo 300ml", "3.49"),
    household("P077", "Garbage bags 20-pack", "2.79"),
]

PRODUCT_BY_ID = {p.product_id: p for p in PRODUCTS}
if len(PRODUCT_BY_ID) != len(PRODUCTS):
    raise RuntimeError("Duplicate product IDs in catalogue")

BASE_CATEGORY_WEIGHTS = {
    PRODUCE: 20,
    DAIRY: 15,
    PROTEIN: 12,
    BAKERY: 12,
    DRINKS: 8,
    SNACKS: 8,
    READY: 7,
    PANTRY: 8,
    HOUSEHOLD: 5,
}

# Intentional synthetic variation makes the three demo personas useful for
# testing different grocery and nutrition insights. These are not real profiles.
PERSONA_CATEGORY_MULTIPLIERS = {
    "CUST02220": {PRODUCE: 0.75, PROTEIN: 0.80, DRINKS: 1.50, SNACKS: 1.80, READY: 1.60, HOUSEHOLD: 0.70},
    "CUST05013": {PRODUCE: 1.20, DAIRY: 1.25, PROTEIN: 1.50, DRINKS: 0.70, SNACKS: 0.65, READY: 0.70, PANTRY: 1.15},
    "CUST00001": {PRODUCE: 1.45, PROTEIN: 1.15, BAKERY: 1.10, DRINKS: 0.70, SNACKS: 0.65, READY: 0.65, HOUSEHOLD: 1.15},
}


@dataclass
class BasketLine:
    product: Product
    quantity: Decimal
    raw_total: Decimal
    line_total: Decimal = Decimal("0")


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fixed(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), f".{places}f")


def quantity_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def slug_hash(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def choose_quantity(product: Product, target_average: Decimal, rng: random.Random) -> Decimal:
    if product.weighted:
        affordable = float(target_average / product.base_price_eur)
        upper = max(0.30, min(1.50, affordable * 1.40))
        return Decimal(str(round(rng.uniform(0.20, upper) * 20) / 20)).quantize(Decimal("0.05"))
    quantity = Decimal("1")
    if product.base_price_eur * 2 <= target_average * Decimal("1.8") and rng.random() < 0.16:
        quantity = Decimal("2")
    return quantity


def make_basket(customer_id: str, target: Decimal, rng: random.Random) -> list[BasketLine]:
    if target < Decimal("12"):
        base_count = max(1, round(float(target / Decimal("3.2"))))
    else:
        base_count = max(3, round(float(target / Decimal("4.4"))))
    base_count = min(base_count, 32)
    persona_weights = PERSONA_CATEGORY_MULTIPLIERS.get(customer_id, {})
    categories = list(BASE_CATEGORY_WEIGHTS)
    best: tuple[Decimal, list[BasketLine]] | None = None

    for _ in range(300):
        count = max(1, min(34, base_count + rng.randint(-2, 2)))
        target_average = target / count
        eligible = [
            p for p in PRODUCTS
            if p.weighted or p.base_price_eur <= max(Decimal("4"), target_average * 4)
        ]
        lines: list[BasketLine] = []
        seen: set[str] = set()
        for _ in range(count):
            weights = [
                BASE_CATEGORY_WEIGHTS[c] * persona_weights.get(c, 1.0)
                for c in categories
            ]
            pool: list[Product] = []
            for _ in range(12):
                category = rng.choices(categories, weights=weights, k=1)[0]
                pool = [p for p in eligible if p.category == category and p.product_id not in seen]
                if pool:
                    break
            if not pool:
                pool = [p for p in eligible if p.product_id not in seen]
            if not pool:
                break
            product = rng.choice(pool)
            seen.add(product.product_id)
            quantity = choose_quantity(product, target_average, rng)
            raw_total = product.base_price_eur * quantity
            lines.append(BasketLine(product, quantity, raw_total))

        raw_total = sum((line.raw_total for line in lines), Decimal("0"))
        if not lines or raw_total <= 0:
            continue
        factor = target / raw_total
        distance = abs(factor - 1)
        if best is None or distance < best[0]:
            best = (distance, lines)
        if Decimal("0.72") <= factor <= Decimal("1.38"):
            break

    if best is None:
        raise RuntimeError(f"Could not build basket for {target} EUR")
    lines = best[1]
    raw_total = sum((line.raw_total for line in lines), Decimal("0"))
    factor = target / raw_total
    if factor < Decimal("0.35") or factor > Decimal("2.75"):
        raise RuntimeError(f"Unrealistic price factor {factor} for {target} EUR basket")

    for line in lines:
        line.line_total = cents(line.raw_total * factor)
    adjustment_index = max(range(len(lines)), key=lambda i: lines[i].line_total)
    lines[adjustment_index].line_total += target - sum(
        (line.line_total for line in lines), Decimal("0")
    )
    if any(line.line_total <= Decimal("0.05") for line in lines):
        raise RuntimeError(f"Invalid reconciled line in {target} EUR basket")
    if sum((line.line_total for line in lines), Decimal("0")) != target:
        raise RuntimeError("Receipt line reconciliation failed")
    return lines


def read_transactions(
    path: Path, merchant_id: str, customer_ids: set[str], limit: int | None
) -> list[dict]:
    selected: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for source_row_number, row in enumerate(csv.DictReader(handle), start=1):
            if row["category"] != "Groceries" or row["merchant_id"] != merchant_id:
                continue
            if row["customer_id"] not in customer_ids:
                continue
            amount = -Decimal(row["tx_amount_eur"])
            if amount <= 0:
                continue
            row["source_row_number"] = source_row_number
            row["receipt_target_eur"] = amount
            selected.append(row)
    selected.sort(
        key=lambda r: (r["customer_id"], r["tx_date"], r["tx_timestamp"], r["source_row_number"])
    )
    return selected[:limit] if limit is not None else selected


def transaction_key(row: dict) -> str:
    stable_fields = "|".join(
        str(row[k])
        for k in (
            "source_row_number",
            "customer_id",
            "bank_account_id",
            "tx_date",
            "tx_timestamp",
            "tx_amount_eur",
            "merchant_id",
            "mcc_code",
        )
    )
    return "tx_" + slug_hash(stable_fields)


def build_dataset(transactions: list[dict], merchant_id: str, seed: int) -> tuple[list[dict], list[dict]]:
    receipts: list[dict] = []
    items: list[dict] = []
    receipt_ids: set[str] = set()

    for row in transactions:
        tx_key = transaction_key(row)
        receipt_id = "RCPT-" + slug_hash("synthetic-prisma:" + tx_key, 16).upper()
        if receipt_id in receipt_ids:
            raise RuntimeError(f"Duplicate receipt ID {receipt_id}")
        receipt_ids.add(receipt_id)
        rng = random.Random(f"{seed}:{receipt_id}")
        target = row["receipt_target_eur"]
        lines = make_basket(row["customer_id"], target, rng)
        raw_basket_total = sum((line.raw_total for line in lines), Decimal("0"))
        food_spend = Decimal("0")
        nutrition_spend = Decimal("0")

        for line_number, line in enumerate(lines, start=1):
            product = line.product
            if product.is_food:
                food_spend += line.line_total
                nutrition_spend += line.line_total
            item = {
                "receipt_id": receipt_id,
                "line_number": line_number,
                "product_id": product.product_id,
                "product_name": product.name,
                "category": product.category,
                "tags": product.tags,
                "quantity": quantity_text(line.quantity),
                "quantity_unit": "kg" if product.weighted else "package",
                "unit_price_eur": fixed(line.line_total / line.quantity, 6),
                "line_total_eur": fixed(line.line_total),
                "catalog_line_total_eur": fixed(line.raw_total, 4),
                "price_delta_vs_catalog_eur": fixed(line.line_total - line.raw_total, 4),
                "nutrition_source": "synthetic_catalog_estimate" if product.is_food else "",
                "nutrition_confidence": fixed(product.nutrition_confidence, 2) if product.is_food else "",
            }
            if product.is_food:
                factor = product.package_size * line.quantity / Decimal("100")
                for nutrient in NUTRIENTS:
                    item[nutrient] = fixed(product.nutrients[nutrient] * factor, 3)
            else:
                for nutrient in NUTRIENTS:
                    item[nutrient] = ""
            items.append(item)

        coverage = nutrition_spend / food_spend * 100 if food_spend else Decimal("0")
        receipts.append({
            "receipt_id": receipt_id,
            "transaction_key": tx_key,
            "source_row_number": row["source_row_number"],
            "customer_id": row["customer_id"],
            "bank_account_id": row["bank_account_id"],
            "merchant_id": merchant_id,
            "store_name": "Prisma Demo",
            "merchant_name": "Prisma",
            "tx_date": row["tx_date"],
            "tx_timestamp": row["tx_timestamp"],
            "currency": "EUR",
            "transaction_total_eur": fixed(target),
            "receipt_total_eur": fixed(target),
            "line_count": len(lines),
            "item_quantity": fixed(sum((line.quantity for line in lines), Decimal("0")), 2),
            "food_spend_eur": fixed(food_spend),
            "non_food_spend_eur": fixed(target - food_spend),
            "nutrition_estimated_spend_eur": fixed(nutrition_spend),
            "food_item_nutrition_coverage_pct": fixed(coverage, 1),
            "basket_price_factor": fixed(target / raw_basket_total, 4),
            "merchant_mapping": "synthetic_not_verified",
            "synthetic": "true",
        })

    return receipts, items


def product_rows() -> list[dict]:
    rows = []
    for product in PRODUCTS:
        row = {
            "product_id": product.product_id,
            "product_name": product.name,
            "brand": "Synthetic Demo",
            "category": product.category,
            "tags": product.tags,
            "base_unit_price_eur": fixed(product.base_price_eur),
            "price_unit": "kg" if product.weighted else "package",
            "package_size": quantity_text(product.package_size) if product.package_size is not None else "",
            "package_unit": product.package_unit,
            "nutrition_per": product.nutrition_per,
            "nutrition_source": "synthetic_catalog_estimate" if product.is_food else "",
            "nutrition_confidence": fixed(product.nutrition_confidence, 2) if product.is_food else "",
            "synthetic": "true",
        }
        for nutrient in NUTRIENTS:
            row[nutrient] = (
                fixed(product.nutrients[nutrient], 3) if product.is_food else ""
            )
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty dataset {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate(receipts: list[dict], items: list[dict], transactions: list[dict]) -> None:
    if len(receipts) != len(transactions):
        raise RuntimeError("Not every selected source transaction received a receipt")
    items_by_receipt: dict[str, list[dict]] = {}
    for item in items:
        if item["product_id"] not in PRODUCT_BY_ID:
            raise RuntimeError(f"Unknown product {item['product_id']}")
        items_by_receipt.setdefault(item["receipt_id"], []).append(item)
    source_total = sum((row["receipt_target_eur"] for row in transactions), Decimal("0"))
    output_total = Decimal("0")
    for receipt in receipts:
        lines = items_by_receipt.get(receipt["receipt_id"], [])
        if len(lines) != receipt["line_count"]:
            raise RuntimeError(f"Wrong line count for {receipt['receipt_id']}")
        if len({line["line_number"] for line in lines}) != len(lines):
            raise RuntimeError(f"Duplicate line number for {receipt['receipt_id']}")
        total = sum((Decimal(line["line_total_eur"]) for line in lines), Decimal("0"))
        if total != Decimal(receipt["transaction_total_eur"]):
            raise RuntimeError(f"Receipt total mismatch for {receipt['receipt_id']}")
        output_total += total
    if output_total != source_total:
        raise RuntimeError("Dataset total does not match selected source transactions")


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    receipts: list[dict],
    items: list[dict],
) -> None:
    category_totals: Counter[str] = Counter()
    for item in items:
        category_totals[item["category"]] += float(item["line_total_eur"])
    manifest = {
        "dataset": "Aino Money synthetic Prisma receipts",
        "version": 1,
        "synthetic": True,
        "generator": "scripts/generate_synthetic_receipts.py",
        "generator_seed": args.seed,
        "source_transactions": Path(args.transactions).name,
        "source_row_number_definition": "1-based transaction data row, excluding the CSV header",
        "merchant_mapping": {
            "merchant_id": args.merchant_id,
            "merchant_name": "Prisma",
            "store_name": "Prisma Demo",
            "verified_against_real_merchant": False,
        },
        "customer_ids": sorted({r["customer_id"] for r in receipts}),
        "receipt_count": len(receipts),
        "receipt_item_count": len(items),
        "product_count": len(PRODUCTS),
        "date_range": [min(r["tx_date"] for r in receipts), max(r["tx_date"] for r in receipts)],
        "receipt_total_eur": fixed(sum((Decimal(r["receipt_total_eur"]) for r in receipts), Decimal("0"))),
        "category_totals_eur": {k: round(v, 2) for k, v in sorted(category_totals.items())},
        "files": {
            "prisma_receipts.csv": "One receipt per selected source grocery transaction",
            "prisma_receipt_items.csv": "Itemized lines with quantities, reconciled prices, and calculated nutrients",
            "prisma_products.csv": "Synthetic generic-product catalogue with nutrients per 100g or 100ml",
        },
        "joins": {
            "receipts_to_items": "prisma_receipts.receipt_id = prisma_receipt_items.receipt_id",
            "items_to_products": "prisma_receipt_items.product_id = prisma_products.product_id",
            "receipts_to_source": "source_row_number is the source CSV data row; transaction_key is a stable synthetic key",
        },
        "nutrition_scope": [
            "All products, item selections, prices, and nutrition values are synthetic.",
            "Nutrition values are plausible generic estimates, not real Prisma or brand product labels.",
            "Sugar is total sugar, not added sugar.",
            "Nutrients describe estimated purchased food, not consumed food or dietary adequacy.",
            "Receipts do not cover restaurant food, other stores, food waste, or sharing within a household.",
        ],
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=Path, default=ROOT / "tx_junction_transactions.txt")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "receipts")
    parser.add_argument("--merchant-id", default="MRC-GRO-0032")
    parser.add_argument(
        "--customer-id",
        action="append",
        dest="customer_ids",
        help="Customer to include; repeat for multiple customers (default: three demo personas)",
    )
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum receipt count")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if not re.fullmatch(r"MRC-GRO-\d{4}", args.merchant_id):
        parser.error("--merchant-id must look like MRC-GRO-0032")
    return args


def main() -> None:
    args = parse_args()
    if not args.transactions.is_file():
        raise SystemExit(f"Transaction file not found: {args.transactions}")
    customer_ids = set(args.customer_ids or DEMO_CUSTOMERS)
    transactions = read_transactions(args.transactions, args.merchant_id, customer_ids, args.limit)
    if not transactions:
        raise SystemExit("No matching grocery transactions found")
    receipts, items = build_dataset(transactions, args.merchant_id, args.seed)
    products = product_rows()
    validate(receipts, items, transactions)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "prisma_receipts.csv", receipts)
    write_csv(args.output_dir / "prisma_receipt_items.csv", items)
    write_csv(args.output_dir / "prisma_products.csv", products)
    write_manifest(args.output_dir / "manifest.json", args, receipts, items)
    total = sum((Decimal(r["receipt_total_eur"]) for r in receipts), Decimal("0"))
    print(
        f"Generated {len(receipts)} receipts, {len(items)} item lines, and "
        f"{len(products)} products for {len(customer_ids)} customers; total {fixed(total)} EUR"
    )
    print(f"Output: {args.output_dir}")


if __name__ == "__main__":
    main()
