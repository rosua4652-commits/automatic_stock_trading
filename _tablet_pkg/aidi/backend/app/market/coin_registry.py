"""코인 심볼 → 한글/영문 명칭 매핑."""

COIN_NAMES: dict[str, tuple[str, str]] = {
    "BTC": ("비트코인", "Bitcoin"),
    "ETH": ("이더리움", "Ethereum"),
    "BNB": ("바이낸스코인", "BNB"),
    "SOL": ("솔라나", "Solana"),
    "XRP": ("리플", "XRP"),
    "ADA": ("에이다", "Cardano"),
    "AVAX": ("아발란체", "Avalanche"),
    "DOT": ("폴카닷", "Polkadot"),
    "LINK": ("체인링크", "Chainlink"),
    "MATIC": ("폴리곤", "Polygon"),
    "POL": ("폴리곤", "Polygon"),
    "LTC": ("라이트코인", "Litecoin"),
    "ATOM": ("코스모스", "Cosmos"),
    "UNI": ("유니스왑", "Uniswap"),
    "NEAR": ("니어", "NEAR"),
    "APT": ("앱토스", "Aptos"),
    "ARB": ("아비트럼", "Arbitrum"),
    "OP": ("옵티미즘", "Optimism"),
    "FIL": ("파일코인", "Filecoin"),
    "INJ": ("인젝티브", "Injective"),
    "SUI": ("수이", "Sui"),
    "DOGE": ("도지코인", "Dogecoin"),
    "SHIB": ("시바이누", "Shiba Inu"),
    "TRX": ("트론", "TRON"),
    "BCH": ("비트코인캐시", "Bitcoin Cash"),
    "ETC": ("이더리움클래식", "Ethereum Classic"),
    "XLM": ("스텔라", "Stellar"),
    "HBAR": ("헤데라", "Hedera"),
    "ICP": ("인터넷컴퓨터", "Internet Computer"),
    "VET": ("비체인", "VeChain"),
    "ALGO": ("알고랜드", "Algorand"),
    "FTM": ("판텀", "Fantom"),
    "SAND": ("샌드박스", "The Sandbox"),
    "MANA": ("디센트럴랜드", "Decentraland"),
    "AAVE": ("에이브", "Aave"),
    "MKR": ("메이커", "Maker"),
    "CRV": ("커브", "Curve"),
    "RUNE": ("토르체인", "THORChain"),
    "SEI": ("세이", "Sei"),
    "TIA": ("셀레스티아", "Celestia"),
    "PEPE": ("페페", "Pepe"),
    "WIF": ("도그위프햇", "dogwifhat"),
    "RENDER": ("렌더", "Render"),
    "FET": ("페치.ai", "Fetch.ai"),
    "TAO": ("비트텐서", "Bittensor"),
    "STX": ("스택스", "Stacks"),
    "IMX": ("이뮤터블", "Immutable"),
    "GRT": ("더그래프", "The Graph"),
    "ENS": ("이더리움네임서비스", "ENS"),
    "LDO": ("리도", "Lido"),
    "AR": ("알위브", "Arweave"),
    "ENA": ("에테나", "Ethena"),
    "WLD": ("월드코인", "Worldcoin"),
    "BONK": ("봉크", "Bonk"),
    "JUP": ("주피터", "Jupiter"),
    "ONDO": ("온도", "Ondo"),
}


def parse_symbol(symbol: str) -> tuple[str, str]:
    s = symbol.upper()
    if s.endswith("USDT"):
        return s[:-4], "USDT"
    if s.endswith("USD"):
        return s[:-3], "USD"
    return s, "USDT"


def coin_meta(symbol: str, base: str | None = None) -> dict[str, str]:
    b = base or parse_symbol(symbol)[0]
    ko, en = COIN_NAMES.get(b, (b, b))
    pair = f"{b}/USDT"
    return {
        "base": b,
        "quote": "USDT",
        "name_ko": ko,
        "name_en": en,
        "pair_label": pair,
        "display": f"{ko} ({b})",
    }
