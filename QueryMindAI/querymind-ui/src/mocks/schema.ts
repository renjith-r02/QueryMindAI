import type { SchemaTable } from "@/types/schema";

/** Add a table here and the Admin → Schema screen picks it up. */
export const TABLES: SchemaTable[] = [
  {
    name: "products",
    blurb: "Catalog and inventory",
    columns: [
      { name: "id", description: "Primary key" },
      { name: "product_name", description: "Display name" },
      { name: "sku", description: "Stock keeping unit" },
      { name: "price", description: "Current price" },
      { name: "category", description: "Merchandising category" },
      { name: "stock_quantity", description: "Units on hand" },
      { name: "reorder_level", description: "Restock threshold" },
    ],
  },
  {
    name: "orders",
    blurb: "Order header",
    columns: [
      { name: "id", description: "Primary key" },
      { name: "customer_id", description: "Customer" },
      { name: "order_date", description: "Placed at" },
      { name: "total_amount", description: "Charged total" },
      { name: "status", description: "placed, shipped, delivered, cancelled" },
      { name: "shipping_method", description: "Standard, express, same-day, pickup" },
    ],
  },
  {
    name: "customers",
    blurb: "Buyer profile",
    columns: [
      { name: "id", description: "Primary key" },
      { name: "full_name", description: "Name" },
      { name: "email", description: "Email, blocked by domain rules" },
      { name: "country", description: "Country" },
      { name: "segment", description: "Loyal, new, at risk, wholesale" },
    ],
  },
  {
    name: "order_items",
    blurb: "Lines on an order",
    columns: [
      { name: "order_id", description: "Order" },
      { name: "product_id", description: "Product" },
      { name: "quantity", description: "Units" },
      { name: "unit_price", description: "Price at purchase" },
    ],
  },
  {
    name: "returns",
    blurb: "Return intake",
    columns: [
      { name: "id", description: "Primary key" },
      { name: "order_id", description: "Original order" },
      { name: "reason", description: "Size or fit, damaged, wrong item, and so on" },
      { name: "created_at", description: "When the return was opened" },
    ],
  },
];
