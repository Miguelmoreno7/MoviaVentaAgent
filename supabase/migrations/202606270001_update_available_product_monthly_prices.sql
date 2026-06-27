update public.movia_products
set monthly_price_mxn = 500,
    updated_at = now()
where slug in ('movia-captura', 'movia-hibrido');
