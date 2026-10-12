import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.services import model_call
from app.services.web_search_service import web_search

_MAX_NAME = 256
_MAX_CATEGORY = 64
_MAX_PRICE = 9_999_999
_PROMPT_TEMPLATE = """
你是商品资料补全助手。以下是搜索到的公开网页资料，请从中提取「{name}」的信息。

要求：
1. 只提取搜索资料能支撑的内容，资料里没有的不要编造；
2. 输出 JSON 对象，格式：
   {{"name": "规范的商品全名", "category": "商品分类", "price": 公开参考价数字或 null, "specs": {{"参数名(AI)": "参数值"}}}}
   其中 name 是规范全名，category 是简短分类（如 耳机、手机、键盘），资料判断不出就填 null；
   price 只能是搜索资料里明确出现的公开标价（单个数字，单位元），资料里没有明确价格就填 null，不要估算；
   specs 里每个键名必须以 (AI) 结尾；
3. 不要输出任何优惠、库存、购买链接；
4. 只输出 JSON 本身，不要解释。

搜索资料：
{materials}
"""

def _build_prompt(name:str,results:list[dict])->str:
    lines =[]
    for r in results:
        text = r.get("summary") or r.get("snippet") or ""
        date = r.get("datePublished") or "未知日期"
        lines.append(f"【{r.get('name') or ''}】{text}(发布于{date})")
    materials = "\n".join(lines) or "(无有效资料)"
    return _PROMPT_TEMPLATE.format(name=name,materials=materials)

def _clean_draft(draft:dict,req_name:str,req_category:str |None)->dict:
    raw_specs = draft.get("specs")
    specs :dict[str,str] = {}
    if isinstance(raw_specs,dict):
        for k,v in raw_specs.items():
            key = str(k).strip()
            if not key or v is None:
                continue
            if not key.endswith("(AI)"):
                key = f"{key}(AI)"
            specs[key] = str(v)
    name = str(draft.get("name") or "").strip()[:_MAX_NAME] or req_name
    category = str(draft.get("category") or "").strip()[:_MAX_CATEGORY] or req_category
    price = draft.get("price")
    # bool 是 int 子类，先排除；非法一律 null——模型嘴里的数字不可信
    if isinstance(price, bool) or not isinstance(price, (int, float)) \
            or price <= 0 or price > _MAX_PRICE:
        price = None
    return {"name": name, "category": category, "price": price, "specs": specs}

async def complete_specs(name:str,category: str |None,user_id:int ,session:AsyncSession)->dict:
    query = f"{category}{name}参数规格" if category else f"{name}参数规格"
    results = await web_search(query,count=5)
    sources = [ r["url"] for r in results if r.get("url")]
    if not results:
        return {"name": name, "category": category, "price": None,
                "specs": {}, "model": None, "sources": []}
    try:
        content,model = await model_call.call_model(user_id,_build_prompt(name,results),session)
    except model_call.ModelCallError as exc:
        raise BizError(ErrorCode.INTERNAL,"模型调用失败，请稍后重试或手动填写") from exc
    try:
        draft = json.loads(content)
        if not isinstance(draft,dict):
            raise ValueError("非json格式")
    except ValueError as exc:
        raise BizError(ErrorCode.INTERNAL,"模型返回了无法解析的内容，请手动填写") from exc
    cleaned = _clean_draft(draft,name,category)
    cleaned["model"] = model
    cleaned["sources"] = sources
    return cleaned