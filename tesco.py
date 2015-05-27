from __future__ import division, absolute_import, unicode_literals
from future_builtins import *

import json
import urlparse

from scrapy.log import ERROR

from product_ranking.items import SiteProductItem
from product_ranking.spiders import BaseProductsSpider, cond_set_value


def brand_at_start(brand):
    return (
        lambda t: t.lower().startswith(brand.lower()),
        lambda _: brand,
        lambda t: t,
    )


class TescoProductsSpider(BaseProductsSpider):
    name = 'tesco_products'
    allowed_domains = ["tesco.com"]

    SEARCH_URL = "http://www.tesco.com/groceries/product/search/default.aspx" \
        "?searchBox={search_term}&newSort=true&search=Search"

    KNOWN_BRANDS = (
        brand_at_start('Dri Pak'),
        brand_at_start('Girlz Only'),
        brand_at_start('Alberto Balsam'),
        brand_at_start('Mum & Me'),
        brand_at_start('Head & Shoulder'),  # Also matcher Head & Shoulders.
        brand_at_start('Ayuuri Natural'),
        (lambda t: ' method ' in t.lower(),
         lambda _: 'Method',
         lambda t: t
         ),
        (lambda t: t.lower().startswith('dr ') or t.lower().startswith('dr. '),
         lambda t: ' '.join(t.split()[:2]),
         lambda t: t,
         ),
    )

    @staticmethod
    def brand_from_title(title):
        for recognize, parse_brand, clean_title \
                in TescoProductsSpider.KNOWN_BRANDS:
            if recognize(title):
                brand = parse_brand(title)
                new_title = clean_title(title)
                break
        else:
            brand = title.split()[0]
            new_title = title
        return brand, new_title

    def parse_product(self, response):
        raise AssertionError("This method should never be called.")

    def _scrape_total_matches(self, response):
        return int(response.css("span.pageTotalItemCount ::text").extract()[0])

    def _scrape_product_links(self, response):
        # To populate the description, fetching the product page is necessary.

        url = response.url

        # This will contain everything except for the URL and description.
        product_jsons = response.xpath(
            "//script[@type='text/javascript']/text()"
        ).re(
            r"\s*tesco\.productData\.push\((\{.+?\})\);"
        )
        if not product_jsons:
            self.log("Found no product data on: %s" % url, ERROR)

        product_links = response.css(
            ".product > .desc > h2 > a ::attr('href')").extract()
        if not product_links:
            self.log("Found no product links on: %s" % url, ERROR)

        for product_json, product_link in zip(product_jsons, product_links):
            prod = SiteProductItem()
            cond_set_value(prod, 'url', urlparse.urljoin(url, product_link))

            product_data = json.loads(product_json)

            cond_set_value(prod, 'price', product_data.get('price'))
            cond_set_value(prod, 'image_url', product_data.get('mediumImage'))

            try:
                brand, title = self.brand_from_title(product_data['name'])
                cond_set_value(prod, 'brand', brand)
                cond_set_value(prod, 'title', title)
            except KeyError:
                raise AssertionError(
                    "Did not find title or brand from JS for product: %s"
                    % product_link
                )

            yield None, prod

    def _scrape_next_results_page_link(self, response):
        next_pages = response.css('p.next > a ::attr(href)').extract()
        next_page = None
        if len(next_pages) == 2:
            next_page = next_pages[0]
        elif len(next_pages) > 2:
            self.log(
                "Found more than two 'next page' link: %s" % response.url,
                ERROR
            )
        return next_page
