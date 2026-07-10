# Runpod public Pods GPU prices

## Qualification

Runpod's public [GPU pricing page](https://www.runpod.io/pricing) server-renders
literal Pods GPU cards with a GPU name, VRAM/HBM field, and a single
USD-per-GPU-hour price. It is usable as a public commercial posted-price
comparator for the GPU-cost panel without creating an account or a deployment.
The authenticated Runpod API is deliberately out of scope: it is account
specific and its availability/endpoint data require a bearer token.

## Collector contract

`orcap capture-gpu --with-runpod` parses only elements that meet all of these
conditions:

1. a `gpu_collection-item` Pods card;
2. one labeled GPU name;
3. one literal `$x/hr` price; and
4. an explicit VRAM or HBM field.

The parser rejects Serverless, Cluster, storage, public-endpoint, contact-sales,
"from" price, unlabeled, and VRAM-free cards. Rows land in
`gpu_published_prices` with `source=runpod`,
`quote_type=published_pods_gpu_list_price`, and raw-page provenance.

## Claim boundary

This is a public list-price surface, not an authenticated availability query,
offer book, reservation quote, utilization statistic, GPU-hour execution
price, provider revenue, or welfare measure. Its hardware labels are not an
automatic exact-equivalence map to the Akash/Vast cohorts used by H47.

The collector is intentionally opt-in and is not connected to the recurring
GPU workflow or a dataset-upload job. That publication decision remains
separate from source qualification.
