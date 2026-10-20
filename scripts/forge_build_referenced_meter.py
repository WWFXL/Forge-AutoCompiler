"""新模板比较双方共同的引用材料计量，旧实验组件不改。"""

from forge_build_full_strategy_runtime import StrategyMeter
from forge_build_full_strategy_runtime_v2 import QualificationAwareMeter
from deerflow.compile.shared_text_packet import SharedTextPacketMixin


class ReferencedStrategyMeter(SharedTextPacketMixin, StrategyMeter):
    """真实双方保持原请求/费用/超时与50k限制。"""


class ReferencedQualificationMeter(SharedTextPacketMixin, QualificationAwareMeter):
    """工程脚本资格共用完全相同的引用编码。"""
