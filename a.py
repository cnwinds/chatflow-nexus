from zai import ZhipuAiClient

client = ZhipuAiClient(api_key="740cec0cf6324f6ab6180db73d354f06.dKApnMcRfFoICgWo")

response = client.web_search.web_search(
   search_engine="search_pro",
   search_query="popular mini games trend 2025",
   count=15,  # 返回结果的条数，范围1-50，默认10
#    search_domain_filter="www.sohu.com",  # 只访问指定域名的内容
   search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
   content_size="high"  # 控制网页摘要的字数，默认medium
)
print(response)