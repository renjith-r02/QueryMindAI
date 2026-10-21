import type { ClarifyOption, QueryResult } from "@/types/query";

export type Intent = {
  id: string;
  suggestion?: string;
  test: (question: string) => boolean;
} & (
  | { kind: "result"; result: QueryResult }
  | { kind: "heal"; result: QueryResult }
  | { kind: "clarify"; options: ClarifyOption[] }
);

const topProducts: QueryResult = {
  explanation:
    "This query joins orders with products through order items, filters to last quarter, and sums the revenue column grouped by product name.",
  sql: `SELECT p.product_name AS product,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.id
JOIN orders o ON oi.order_id = o.id
WHERE o.order_date >= DATE_TRUNC('quarter', CURRENT_DATE) - INTERVAL '3 months'
  AND o.order_date < DATE_TRUNC('quarter', CURRENT_DATE)
GROUP BY p.product_name
ORDER BY revenue DESC
LIMIT 10;`,
  columns: [
    { key: "product", label: "Product" },
    { key: "revenue", label: "Revenue" },
  ],
  rows: [
    { product: "Wireless Headphones", revenue: 156790 },
    { product: "Smart Watch", revenue: 101235 },
    { product: "Running Shoes", revenue: 76543 },
    { product: "4K Smart TV", revenue: 74210 },
    { product: "Laptop Stand", revenue: 54890 },
    { product: "Cotton T-Shirt", revenue: 47120 },
    { product: "Mechanical Keyboard", revenue: 38940 },
    { product: "Yoga Mat", revenue: 28765 },
    { product: "Backpack", revenue: 23457 },
    { product: "USB-C Hub", revenue: 18220 },
  ],
};

const monthly: QueryResult = {
  explanation: "This query joins orders with order items, keeps the last six months, and sums revenue for each month.",
  sql: `SELECT DATE_TRUNC('month', o.order_date) AS month,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'
GROUP BY month
ORDER BY month;`,
  columns: [
    { key: "month", label: "Month" },
    { key: "revenue", label: "Revenue" },
  ],
  rows: [
    { month: "Nov 2025", revenue: 412000 },
    { month: "Dec 2025", revenue: 538400 },
    { month: "Jan 2026", revenue: 390200 },
    { month: "Feb 2026", revenue: 421800 },
    { month: "Mar 2026", revenue: 467500 },
    { month: "Apr 2026", revenue: 502900 },
  ],
};

const lowStock: QueryResult = {
  explanation:
    "This query lists catalog products whose stock is at or below the reorder level, sorted by the smallest stock first.",
  sql: `SELECT p.product_name AS product,
       p.category AS category,
       p.stock_quantity AS stock
FROM products p
WHERE p.stock_quantity <= p.reorder_level
ORDER BY p.stock_quantity ASC
LIMIT 10;`,
  columns: [
    { key: "product", label: "Product" },
    { key: "category", label: "Category" },
    { key: "stock", label: "Stock" },
  ],
  rows: [
    { product: "Noise Cancelling Earbuds", category: "Electronics", stock: 4 },
    { product: "Running Shoes", category: "Footwear", stock: 6 },
    { product: "Ceramic Pour-Over", category: "Home", stock: 7 },
    { product: "Wool Beanie", category: "Apparel", stock: 8 },
    { product: "Trail Backpack", category: "Outdoors", stock: 9 },
  ],
};

const category: QueryResult = {
  explanation: "This query joins order items to products and sums revenue for each product category.",
  sql: `SELECT p.category AS category,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.id
GROUP BY p.category
ORDER BY revenue DESC;`,
  columns: [
    { key: "category", label: "Category" },
    { key: "revenue", label: "Revenue" },
  ],
  rows: [
    { category: "Electronics", revenue: 128743 },
    { category: "Home & Kitchen", revenue: 86531 },
    { category: "Fashion", revenue: 64299 },
    { category: "Beauty", revenue: 38766 },
    { category: "Sports & Outdoors", revenue: 27489 },
  ],
};

const shipping: QueryResult = {
  explanation: "This query counts orders and groups them by the shipping method on the order.",
  sql: `SELECT o.shipping_method AS method,
       COUNT(*) AS orders
FROM orders o
GROUP BY o.shipping_method
ORDER BY orders DESC;`,
  columns: [
    { key: "method", label: "Shipping method" },
    { key: "orders", label: "Orders" },
  ],
  rows: [
    { method: "Standard", orders: 18420 },
    { method: "Express", orders: 9320 },
    { method: "Same-day", orders: 4188 },
    { method: "Store pickup", orders: 2764 },
  ],
};

const segments: QueryResult = {
  explanation:
    "This query joins customers to orders and sums revenue for each customer segment over the last six months.",
  sql: `SELECT c.segment AS segment,
       SUM(o.total_amount) AS revenue
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months'
GROUP BY c.segment
ORDER BY revenue DESC;`,
  columns: [
    { key: "segment", label: "Segment" },
    { key: "revenue", label: "Revenue" },
  ],
  rows: [
    { segment: "Loyal", revenue: 640200 },
    { segment: "New", revenue: 318400 },
    { segment: "At risk", revenue: 142800 },
    { segment: "Wholesale", revenue: 98600 },
  ],
};

const returns: QueryResult = {
  explanation: "This query counts return records and groups them by the reason captured at intake.",
  sql: `SELECT r.reason AS reason,
       COUNT(*) AS returns
FROM returns r
GROUP BY r.reason
ORDER BY returns DESC;`,
  columns: [
    { key: "reason", label: "Reason" },
    { key: "returns", label: "Returns" },
  ],
  rows: [
    { reason: "Size or fit", returns: 842 },
    { reason: "Changed mind", returns: 610 },
    { reason: "Damaged", returns: 274 },
    { reason: "Wrong item", returns: 196 },
    { reason: "Late delivery", returns: 121 },
  ],
};

const orderTotal: QueryResult = {
  explanation: "This query reads the pre-aggregated total on the orders table and sums it for last month.",
  sql: `SELECT SUM(o.total_amount) AS total_amount
FROM orders o
WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 months'
  AND o.order_date < DATE_TRUNC('month', CURRENT_DATE);`,
  columns: [
    { key: "metric", label: "Metric" },
    { key: "total_amount", label: "Total amount" },
  ],
  rows: [{ metric: "Last month · orders.total_amount", total_amount: 502900 }],
};

const lineTotal: QueryResult = {
  explanation:
    "This query multiplies unit price by quantity on order items and sums that computed amount for last month.",
  sql: `SELECT SUM(oi.unit_price * oi.quantity) AS total_amount
FROM order_items oi
JOIN orders o ON oi.order_id = o.id
WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 months'
  AND o.order_date < DATE_TRUNC('month', CURRENT_DATE);`,
  columns: [
    { key: "metric", label: "Metric" },
    { key: "total_amount", label: "Total amount" },
  ],
  rows: [{ metric: "Last month · unit price × quantity", total_amount: 486440 }],
};

const heal: QueryResult = {
  explanation:
    "This query joins products to order items and sums sales. The first attempt compared a text price column and failed; the retry casts price to numeric.",
  sql: `SELECT p.product_name AS product,
       p.category AS category,
       SUM(oi.quantity) AS quantity,
       SUM(oi.quantity * CAST(p.price AS NUMERIC)) AS total_sales
FROM products p
JOIN order_items oi ON oi.product_id = p.id
WHERE CAST(p.price AS NUMERIC) >= 20
GROUP BY p.product_name, p.category
ORDER BY total_sales DESC
LIMIT 5;`,
  columns: [
    { key: "product", label: "Product" },
    { key: "category", label: "Category" },
    { key: "quantity", label: "Quantity" },
    { key: "total_sales", label: "Total sales" },
  ],
  rows: [
    { product: "Wireless Headphones", category: "Electronics", quantity: 1245, total_sales: 156790 },
    { product: "Smart Watch", category: "Electronics", quantity: 843, total_sales: 101235 },
    { product: "Cotton T-Shirt", category: "Apparel", quantity: 2356, total_sales: 47120 },
    { product: "Running Shoes", category: "Footwear", quantity: 1102, total_sales: 76543 },
    { product: "Backpack", category: "Accessories", quantity: 672, total_sales: 23457 },
  ],
  heal: {
    brokenSql: `SELECT p.product_name, SUM(p.price) AS total_sales
FROM products p
JOIN order_items oi ON oi.product_id = p.id
WHERE p.price >= '20'
GROUP BY p.product_name;`,
    note: "Root cause: type mismatch on price (text compared with a number). Applied CAST(price AS NUMERIC) and ran the query once more.",
  },
};

/**
 * First matching intent wins. Add a question by inserting an object here.
 * Put specific matches above the broad product/revenue fallback.
 */
export const INTENTS: Intent[] = [
  {
    id: "amount",
    suggestion: "Show total amount last month",
    kind: "clarify",
    test: (q) =>
      /\b(total amount|amount last|show amount)\b/.test(q) && !/\b(unit price|line item|order total)\b/.test(q),
    options: [
      {
        id: "orders",
        title: "orders.total_amount",
        detail: "Pre-aggregated total stored on the order, including discounts and tax.",
        result: orderTotal,
      },
      {
        id: "lines",
        title: "unit price × quantity",
        detail: "Computed from order item lines. Use this when the order total is not trusted.",
        result: lineTotal,
      },
    ],
  },
  {
    id: "heal",
    suggestion: "Product sales summary",
    kind: "heal",
    test: (q) => /\b(self-heal|self heal|type mismatch|sales summary|product sales)\b/.test(q),
    result: heal,
  },
  {
    id: "stock",
    suggestion: "Low stock products by category",
    kind: "result",
    test: (q) => /\b(low stock|out of stock|reorder|inventory)\b/.test(q),
    result: lowStock,
  },
  {
    id: "monthly",
    suggestion: "Monthly sales trend for 2026",
    kind: "result",
    test: (q) => /\b(month|trend|over time)\b/.test(q),
    result: monthly,
  },
  {
    id: "category",
    suggestion: "Revenue by product category",
    kind: "result",
    test: (q) => /\b(categor)/.test(q),
    result: category,
  },
  {
    id: "shipping",
    suggestion: "Orders by shipping method",
    kind: "result",
    test: (q) => /\b(ship|pickup|fulfill)/.test(q),
    result: shipping,
  },
  {
    id: "segments",
    kind: "result",
    test: (q) => /\b(segment|customer)\b/.test(q),
    result: segments,
  },
  {
    id: "returns",
    kind: "result",
    test: (q) => /\breturn/.test(q),
    result: returns,
  },
  {
    id: "products",
    suggestion: "Top 10 products by revenue last quarter",
    kind: "result",
    test: (q) => /\b(product|revenue|top|best|sales|sell)/.test(q),
    result: topProducts,
  },
];

export const SUGGESTIONS = INTENTS.flatMap((intent) => (intent.suggestion ? [intent.suggestion] : []));
