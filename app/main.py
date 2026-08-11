from fastapi import FastAPI
from pydantic import BaseModel
from strategy.decision_engine import make_decision
from journal.trade_logger import log_trade
from exchange.market_data import get_market_data


app = FastAPI()


class WebhookData(BaseModel):
    symbol: str
    signal: str
    price: float
   

@app.get("/")
def root():
    return {"message": "Trading Bot is Running!"}


@app.post("/webhook")
async def webhook(data: WebhookData):
    market_data = get_market_data(data.symbol)


    print(f"Funding Rate: {market_data['funding_rate']}")
    print(f"Open Interest Change: {market_data['open_interest_change']}")
    print(f"Volume Ratio: {market_data['volume_ratio']}")
    print(f"Market Structure: {market_data['market_structure']}")
    print(f"BOS: {market_data['bos']}")
    print(f"BOS Quality: {market_data['bos_quality']}")
    print(f"CHOCH: {market_data['choch']}")
    print(f"Liquidity Sweep: {market_data['liquidity_sweep']}")


    result = make_decision(
    signal=data.signal,
    liquidity_sweep=market_data["liquidity_sweep"],
    liquidity_strength=market_data["liquidity_strength"],
    market_structure=market_data["market_structure"],
    bos_quality=market_data["bos_quality"],
    choch=market_data["choch"],
    volume_ratio=market_data["volume_ratio"],
    open_interest_change=market_data["open_interest_change"],
    funding_rate=market_data["funding_rate"]
)


    log_trade({
       "symbol": data.symbol,
       "signal": data.signal,
       "price": data.price,
       "liquidity_strength": market_data["liquidity_strength"],
       "volume_ratio": market_data["volume_ratio"],
       "open_interest_change": market_data["open_interest_change"],
       "funding_rate": market_data["funding_rate"],
       "decision": result["decision"],
       "score": result["score"],
       "liquidity_score": result["liquidity_score"],
       "volume_score": result["volume_score"],
       "open_interest_score": result["open_interest_score"],
       "funding_score": result["funding_score"]


   })


    print(f"Signal received: {data.signal}")
    print(f"Decision: {result['decision']}")
    print(f"Score: {result['score']}")
    print(f"Liquidity Score: {result['liquidity_score']}")
    print(f"Volume Score: {result['volume_score']}")
    print(f"Open Interest Score: {result['open_interest_score']}")
    print(f"Funding Score: {result['funding_score']}")

 
    return {
        "status": "received",
        "symbol": data.symbol,
        "signal": data.signal,
        "price": data.price,
        "decision": result["decision"],
        "score": result["score"]


    }
