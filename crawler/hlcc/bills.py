# -*- coding: utf-8 -*-
import re
import urllib
from urlparse import urljoin
import scrapy
from scrapy.http import Request, FormRequest
from scrapy.selector import Selector
from hlcc.items import Bills
import logging
import json
import os


class FieldHandler(object):
    def __init__(self, field_name, wrapper=None):
        self.field_name = field_name
        self.wrapper = wrapper

    def fill_field(self, item, value):
        if self.wrapper:
            value = self.wrapper(value)

        item[self.field_name] = value

        return item


class ListFieldHandler(FieldHandler):

    def fill_field(self, item, value):
        if self.wrapper:
            value = self.wrapper(value)

        if self.field_name not in item:
            item[self.field_name] = []

        item[self.field_name].append(value)

        return item


def text(value):
    value = map(lambda item: item.strip(), value)
    return "\n".join(value)


def number(value):
    tmp = "".join(value)
    return int(tmp.strip())

def split_orz_format(value):
    # If there is only 1 value, try to split the value by 、(\u3001)|，(\uff0c)|。(\u3002),
    # Because format is not consistent
    if len(value) == 1:
        tmp = value[0].strip()

        split_token = None

        if u"\uff0c" in tmp:
            split_token = u"\uff0c"
        elif u"\u3002" in tmp and (not tmp.endswith(u"\u3002") if tmp.count(u"\u3002") == 1 else True):
            split_token = u"\u3002"
        elif u"\u3001" in tmp:
            split_token = u"\u3001"

        value = tmp.split(split_token)

    return [item.strip() for item in value if item]

class Spider(scrapy.Spider):
    name = "bills"
    allowed_domains = ["www.hlcc.gov.tw"]
    start_urls = ["http://www.hlcc.gov.tw/case-1.php",
                  "http://www.hlcc.gov.tw/case-2.php",
                  "http://www.hlcc.gov.tw/case-3.php",
                  "http://www.hlcc.gov.tw/case-4.php"]

    download_delay = 0.1

    ROOT_URL = "http://www.hlcc.gov.tw/"

    def __init__(self):
        with open(os.path.join(os.path.dirname(__file__), "special_bills.json"), "r") as special_bills_file:
            self.special_bills = json.load(special_bills_file)

    def parse(self, response):
        sel = Selector(response)
        pages = sel.xpath('//div[contains(@class, "area-2")]//select[@name="select2"]/option/@value').extract()

        print pages
        for page in pages:
            yield Request(self.ROOT_URL + page, self.parse_page)

    def parse_page(self, response):
        sel = Selector(response)
        links = sel.xpath('//div[contains(@class, "area-2")]//a[@class="naz"]/@href').extract()

        for link in links:
            yield Request(self.ROOT_URL + link, self.parse_bill)

    handler_map = {
        u"類別": FieldHandler("category", text),
        u"案號": FieldHandler("bill_no", number),
        u"提案人": FieldHandler("proposed_by", split_orz_format),
        u"請願人": FieldHandler("proposed_by", split_orz_format),
        u"提案單位": FieldHandler("proposed_by", split_orz_format),
        u"案由": FieldHandler("abstract", text),
        u"連署人": FieldHandler("petitioned_by", split_orz_format),
        u"執行情形": FieldHandler("execution", text),
        u"辦法": FieldHandler("methods", text),
        u"審查意見": ListFieldHandler("motions", lambda value: {"date": None, "motion": "審查意見", "resolution": text(value)}),
        u"議決": ListFieldHandler("motions", lambda value: {"date": None, "motion": "議決", "resolution": text(value)})
    }

    election_year_map = {
        u"第14屆": "1998",
        u"第15屆": "2002",
        u"第16屆": "2005",
        u"第17屆": "2009"
    }

    def parse_bill(self, response):
        sel = Selector(response)
        item = Bills()

        # Because there are some bills format with error, I manually save the bill data in the special_bills.json.
#       if response.url in self.special_bills:
#          item.update(self.special_bills[response.url])
#          return item

        tmp = sel.xpath('//div[@class="area-2"]/table/tr[2]/td[@class="td-content"]/text()').extract()[0].split()

        item["resolusion_sitting"] = " ".join(tmp[:-1])
        election = item["resolusion_sitting"].split()[0]

        item["election_year"] = self.election_year_map[election]
        item["county"] = u"花蓮縣"

        item["type"] = tmp[-1]
        item["links"] = response.url
        item["id"] = re.match(r".*index_no=([\d]+)", response.url).group(1)

        rows = sel.xpath('//div[@class="area-2"]/table/tr[4]//tr')

        for row in rows:
            field_name = row.xpath("td[1]/text()").extract()[0]
            field_value = row.xpath("td[2]/text()").extract()

            handler = self.handler_map.get("".join(field_name.split()))

            if handler:
                handler.fill_field(item, field_value)

        return item

