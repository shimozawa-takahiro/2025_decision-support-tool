# calc.py
import math
from pyscipopt import Model, quicksum
import networkx as nx
import folium
from folium.features import Tooltip
import csv

# 設定ファイル
layer_network_list = ["11月", "12月", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月"]
num_product_list = ['鋼材','モジュール', 'ハーフボディ1', 'ハーフボディ3', '浮体基礎', '風車', '風車（設置済）','船舶']
sign = ['plus', 'minus']

# 基地港湾 → 設置海域の傭船料
# 1日あたり
ship_installation_cost = 10100000
# それ以外の傭船料
# 1日あたり
ship_foundation_cost = 2 * 1487000 # 2隻分
# 燃料コスト 往復・1kmあたり燃料費・ポンド換算
ship_fuel_cost = 2 * 333 * 198 # 2隻分,1kmあたり


class Node:
    def __init__(self):
        # ノード名
        self.name = None
        # ノードの月
        self.month = None
        # ノード名＋月 → ノードが一意に決まる
        self.node_id = f"({self.name}_{self.month})"

        # ノードの緯度
        self.lat = None
        # ノードの経度
        self.lon = None

        # ノードの種類 → 小型造船所、中型造船所、大型造船所、基地港湾、設置海域、なし（仮置のみ）
        self.kind = None
        # ノードの役割 → モジュール製作、ハーフボディ1製作、ハーフボディ3製作、浮体基礎製作、洋上での浮体基礎製作、風車組立、風車設置、仮置
        self.role = {}

        # コスト → roleがTrueの場合csvから値を受け取り、Falseの場合はNone
        self.cost = {}
        # キャパシティ → roleがTrueの場合csvから値を受け取り、Falseの場合はNone
        self.capacity = {}
        
        # 仮置キャパシティ → 仮置の場合のみcsvから値を受け取り、それ以外はNone
        self.wet_storage_capacity = None
        # 仮置コスト → 仮置の場合のみcsvから値を受け取り、それ以外はNone
        self.wet_storage_cost = None

        # 鋼材の供給量をcsvから受け取る
        self.steel = None
        # 風車の需要数 → 風車設置: Trueの場合csvから値を受け取り、それ以外はNone
        self.turbine = None

        # 計算用の需要供給量
        self.calc_supply_demand = {}



class Transportation_Edge:
    def __init__(self):
        # 元のnode_id、Node型
        self.source = None
        # 先のnode_id、Node型
        self.target = None
        # 月
        self.month = None

        # 機能決定
        self.function = "輸送"

        # コスト → csvから各部材のコストを順番に受け取る
        self.cost = {}
        # キャパシティ → csvから各部材のキャパシティを順番に受け取る
        self.capacity = {}

        # 最適化変数
        self.flow = {}
        # 最適化変数と同じ値だが、表計算のために用いる
        self.flow_value = {}

        # 計算用のコスト・キャパシティ
        self.calc_cost = {}
        self.calc_capacity = {}



class Production_Edge:
    def __init__(self):
        # 元のnode_id、Node型
        self.source = None
        # 先のnode_id、Node型
        self.target = None

        # 機能決定
        self.function = None

        # コスト → functionによってNode.costのあるvalueからコストを受け取る
        self.cost = None
        # キャパシティ → functionによってNode.capacityのあるvalueのキャパシティを受け取る
        self.capacity = None

        # 最適化変数
        self.flow = {}

        # 計算用のコスト・キャパシティ
        self.calc_cost = {}
        self.calc_capacity = {}



class Storage_Edge:
    def __init__(self):
        # 元のnode_id、Node型
        self.source = None
        # 先のnode_id、Node型
        self.target = None
        # 月
        self.month = None

        # 機能決定
        self.function = "仮置"
        
        # コスト → Node.costの"仮置"valueから値を受け取る
        self.cost = None
        # キャパシティ → Node.capacityの"仮置"valueから値を受け取る
        self.capacity = None

        # 最適化変数
        self.flow = {}
        # 最適化変数と同じ値だが、表計算のために用いる
        self.flow_value = {}

        # 計算用のコスト・キャパシティ
        self.calc_cost = {}
        self.calc_capacity = {}


# 実行関数
def optimize(node_rows, edge_rows):
    # 問題設定
    model: Model = Model('sample')
    # ノードリストを格納するリスト
    node_list: list[Node] = []
    # 輸送リストを格納するリスト
    transportation_list: list[Transportation_Edge] = []
    # 製作リストを格納するリスト
    production_list: list[Production_Edge] = []
    # 仮置リストを格納するリスト
    storage_list: list[Storage_Edge] = []

    # node_rows は List[List[str]] として渡されているので
    # そのまま 1 行ずつ処理します
    # ノード用のCSVファイルを読み込む
    if isinstance(node_rows, str):
        f_node = open(node_rows, encoding='utf-8-sig')
        reader_node = csv.reader(f_node)
    else:
        # 既に TextIOWrapper なのでそのまま
        reader_node = csv.reader(node_rows)
    next(reader_node, None)     # ヘッダーをスキップ
    for row in reader_node:
        if not row or not row[0]:
            continue
        # 繰り返しでlayer_network_list個生成
        for index, month in enumerate(layer_network_list):
            # Nodeクラスを作成
            node = Node()
            # 相生
            node.name = row[0]
            # "11月"
            node.month = month
            node.node_id = f"({node.name}_{node.month})"

            # 緯度、経度を取得
            node.lat = float(row[1])
            node.lon = float(row[2])

            # 小型造船所、中型造船所、大型造船所、基地港湾、設置海域、なし（仮置のみ）
            node.kind = row[3]

            # node.roleを一旦決定
            node.role = {"モジュール製作": False, "ハーフボディ1製作": False, "ハーフボディ3製作": False, "浮体基礎製作": False, "洋上での浮体基礎製作": False, "風車組立": False, "風車設置": False, "仮置": False}
            # 役割に応じてTrueを決定
            if node.kind == "小型造船所":
                node.role["モジュール製作"] = True
                node.role["ハーフボディ1製作"] = True
            
            elif node.kind == "中型造船所":
                node.role["モジュール製作"] = True
                node.role["ハーフボディ1製作"] = True
                node.role["ハーフボディ3製作"] = True
            
            elif node.kind == "大型造船所":
                node.role["モジュール製作"] = True
                node.role["ハーフボディ1製作"] = True
                node.role["ハーフボディ3製作"] = True
                node.role["浮体基礎製作"] = True
            
            elif node.kind == "基地港湾":
                node.role["風車組立"] = True
            
            elif node.kind == "設置海域":
                node.role["風車設置"] = True


            # 仮置を行うかを自分で決定
            if row[4] == "TRUE":
                node.role["仮置"] = True
                # 仮置のコスト
                node.wet_storage_cost = float(row[5]) if row[5] else None
                # 仮置の数 
                node.wet_storage_capacity = int(row[6]) if row[6] else None
            else:
                node.role["仮置"] = False
                node.wet_storage_cost = 0
                node.wet_storage_capacity = 0
            # 洋上での浮体基礎製作を行うかを自分で決定
            if row[7] == "TRUE":
                node.role["洋上での浮体基礎製作"] = True
            else:
                node.role["洋上での浮体基礎製作"] = False


            """ 小数に対応したコスト計算 """               
            # indexが0（初月の場合）sssを初期化
            if index == 0:
                # ノードが持っている各roleのcapacityの小数部分を格納する辞書
                # {'モジュール製作': 0.5, 'ハーフボディ1製作': 0.5}
                sss = {}
                # 初月は初期化
                for task, is_active in list(node.role.items())[:-1]: # -1で仮置を除外
                    if is_active:
                        # 0で初期化
                        sss[task] = 0
            
            # 繰り返し
            for task_index, (task, is_active) in enumerate(list(node.role.items())[:-1]): # -1で仮置を除外
                # モジュール製作だけは特別（CSV:x基分で設定、キャパシティ:4個=1基分で数が違うため）
                if task == "モジュール製作":
                        sss[task] = sss[task] + float(row[10 + 3 * task_index]) if row[10 + 3 * task_index] else 0
                        # capacityの整数部分をnode.capacity[task]に格納
                        node.capacity[task] = 4 * int(sss[task])
                        # 小数部分をsssに格納
                        sss[task] = sss[task] - node.capacity[task]/4
                
                # それ以外のrole
                else:                    
                    if is_active: # モジュール製作、ハーフボディ1製作 ･･･ と繰り返し    
                        sss[task] = sss[task] + float(row[10 + 3 * task_index]) if row[10 + 3 * task_index] else 0
                        # capacityの整数部分をnode.capacity[task]に格納
                        node.capacity[task] = int(sss[task])
                        # 残りをsssに格納
                        sss[task] = sss[task] - node.capacity[task]

                

            # モジュール製作 → ハーフボディ1製作 ･･･ と繰り返しでCSVからコストを受け取る、Falseの場合は初期化した値
            for task_index, (task, is_active) in enumerate(list(node.role.items())[:-1]): # -1で仮置を除外
                if is_active:
                    # コストとキャパシティを適切なインデックスから取得、ミスした場合はNone
                    node.cost[task] = float(row[9 + 3 * task_index]) if row[9 + 3 * task_index] else None
                    # node.capacity[task] = float(row[9 + 3 * task_index]) if row[9 + 3 * task_index] else None
                
                # 風車設置が何月から行えるか
                # プロジェクトが2年以上の場合は未定
                if node.role["風車設置"] == True:
                    # csvから受け取った月より前の時期は風車設置不可能
                    if layer_network_list.index(month) >= layer_network_list.index(f"{row[31]}月"):# 整数
                        node.capacity["風車設置"] = int(row[28]) if row[28] else 0
                    else:
                        node.capacity["風車設置"] = 0


            # 鋼材の供給量
            node.steel = int(row[29]) if row[29] else int(0)
            # 風車の需要量
            node.turbine = int(0)

            # node_listに追加
            node_list.append(node)
            # 各node_listを表示
            # print(f"Node 場所: {node.node_id}, 種類: {node.kind}, 役割: {node.role}, コスト: {node.cost}, キャパシティ: {node.capacity}, 仮置コスト: {node.wet_storage_cost}, 仮置キャパシティ: {node.wet_storage_capacity}, 鋼材: {node.steel}")


        
            # Production_Edgeを追加する場合はここ
            for task, is_active in list(node.role.items())[:-1]: # -1で仮置を除外
                if is_active:
                    # roleのvalueがTrueの場合に、グラフループ=Production_Edgeクラスを作成
                    production_edge = Production_Edge()
                    # node_listから対応するnode_idを取得（これやらないとstr型判定喰らう）
                    node_year = node_list[[x.node_id for x in node_list].index(f'({node.name}_{month})')]
                    # 流出元、流出先を設定（グラフループなので同じ）
                    production_edge.source = node_year
                    production_edge.target = node_year
                    # 機能を設定、モジュール製作、ハーフボディ1製作、ハーフボディ3製作、浮体基礎製作、洋上での浮体基礎製作、風車組立、風車設置
                    production_edge.function = task
                    # 処理コストを設定
                    production_edge.cost = node.cost[task]
                    # 処理キャパシティを設定
                    production_edge.capacity = node.capacity[task]
                    # production_listに追加                       
                    production_list.append(production_edge)
                    # 各成分を表示
                    # print(f"Production_Edge 場所: {production_edge.source.node_id} -> {production_edge.target.node_id}, 機能: {production_edge.function}, {task}コスト: {production_edge.cost}, {task}キャパシティ: {production_edge.capacity}")



            # Storage_Edgeをここで追加
            # 最初の月以外の場合、その前の月からその月への仮置エッジを追加（仮置: Falseの場合でも追加）
            if index != 0:          
                # 仮置のエッジを作成（仮置: Falseの場合でも追加）
                storage_edge = Storage_Edge()
                # node_listから対応するnode_idを取得（これやらないとstr型判定喰らう）
                node_from_year = node_list[[x.node_id for x in node_list].index(f'({node.name}_{layer_network_list[index - 1]})')]
                node_to_year = node_list[[x.node_id for x in node_list].index(f'({node.name}_{month})')]
                # 流出元、流出先を設定
                storage_edge.source = node_from_year
                storage_edge.target = node_to_year

                storage_edge.month = layer_network_list[index - 1]
                # 機能 = 仮置
                storage_edge.function = "仮置"
                # 仮置コスト
                storage_edge.cost = node.wet_storage_cost
                # 仮置キャパシティ
                storage_edge.capacity = node.wet_storage_capacity
                # storage_listに追加
                storage_list.append(storage_edge)
                # 各成分を表示
                # print(f"Storage_Edge 場所: {storage_edge.source.node_id} -> {storage_edge.target.node_id}, 機能: {storage_edge.function}, 仮置コスト: {storage_edge.cost}, 仮置キャパシティ: {storage_edge.capacity}")



        # 風車需要を定数で置くためのノード            
        if row[3] == "設置海域":
            # 各月の設置海域ノードを重ねたもの
            node = Node()
            node.name = row[0]
            # 緯度、経度
            node.lat = float(row[1])
            node.lon = float(row[2])

            # 月の値には意味なし
            node.month = "10000月"
            node.node_id = f"({node.name}_{node.month})"

            node.kind = row[3]
            node.role["風車設置"] = True

            # 鋼材の供給量
            node.steel = int(0)
            # 風車の需要数
            node.turbine = int(row[30]) if row[30] else int(0)               
            # node_listに追加
            node_list.append(node)
            # 各成分を表示
            # print(f"定数用Node 場所: {node.node_id}, 風車需要数: {node.turbine}")

            # for文で設置海域（毎月） → 設置海域（まとめたやつ）エッジ作成
            for month in layer_network_list:
                # 各月のノード
                node_1 = node_list[[x.node_id for x in node_list].index(f'({node.name}_{month})')]
                # 各月の設置海域ノードとまとめた設置海域ノードを結ぶエッジを作成
                transportation_edge = Transportation_Edge()
                transportation_edge.source = node_1
                transportation_edge.target = node
                transportation_edge.function = "輸送"
                # コスト、キャパシティはあらかじめ決めておく
                transportation_edge.cost = {key: int(0) for key in num_product_list}
                transportation_edge.capacity = {key: int(10000) for key in num_product_list}
                # transportation_listに追加
                transportation_list.append(transportation_edge)





    # edge_rows は List[List[str]] として渡されているので
    if isinstance(edge_rows, str):
        f_edge = open(edge_rows, encoding='utf-8-sig')
        reader_edge = csv.reader(f_edge)
    else:
        reader_edge = csv.reader(edge_rows)
    next(reader_edge, None)
    for row in reader_edge:
        if not row or not row[0]:
            continue
        # 流出元、流出先の名前を取得
        source_name = row[0]
        target_name = row[1]

        # 名前を取得したらlayer_network_listだけ繰り返す
        for month in layer_network_list:
            # ラベルからNodeクラスの"node_id"属性を取得
            source_node = node_list[[x.node_id for x in node_list].index(f'({source_name}_{month})')]
            target_node = node_list[[x.node_id for x in node_list].index(f'({target_name}_{month})')]

            # 輸送エッジの作成
            transportation_edge = Transportation_Edge()
            # 流出元、流出先を設定
            transportation_edge.source = source_node
            transportation_edge.target = target_node
            # 月を設定
            transportation_edge.month = month

            # 機能を設定
            transportation_edge.function = "輸送"

            # コストとキャパシティを設定                
            # 鋼材 → モジュール → ハーフボディ1 ･･･ → 風車（設置済）と繰り返しでCSVからコスト & キャパシティを受け取る（costとcapacityを辞書型にしたので）、船舶は別で追加
            for data, product_id in enumerate(num_product_list[:-1]):
                # 辞書に値を設定（値が存在しない場合はNone）
                transportation_edge.cost[product_id] = int(0) # コストは0
                transportation_edge.capacity[product_id] = int(1000) # キャパシティは無限

            # 船舶輸送のコストとキャパシティを設定
            # 基地港湾 → 設置海域の場合は浮体基礎の輸送の場合とコストが異なる               
            if source_node.kind == "基地港湾" and target_node.kind == "設置海域":
                transportation_edge.cost["船舶"] = 2 * ship_installation_cost * (math.ceil(int(row[3])/(24*10*1.852))) + int(row[3]) # 速度は10ノット
                transportation_edge.capacity["船舶"] = row[4] # キャパシティは無限                
            else:
                transportation_edge.cost["船舶"] = 2 * ship_foundation_cost * (math.ceil(int(row[3])/(24*5*1.852))) + int(row[3]) # 速度は5ノット
                transportation_edge.capacity["船舶"] = row[4]

            # 2 * ship_foundation_cost * (math.ceil(int(row[3])/(24*5*1.852))) + int(row[3]) # 速度は5ノット
            # transportation_listに追加
            transportation_list.append(transportation_edge)

    # 需給
    for node in node_list:
        for product_id in num_product_list:
            # 鋼材の供給量と風車の需要数は入力値を使う
            if product_id == "鋼材":
                node.calc_supply_demand[node.node_id, product_id] = node.steel

            elif product_id == "風車（設置済）": # 10000月はlayer_network_listの設置海域をまとめたノード
                node.calc_supply_demand[node.node_id, product_id] = - node.turbine
            # それ以外の部材については0
            else:
                node.calc_supply_demand[node.node_id, product_id] = int(0)

    # transportation_listの計算用コスト・キャパシティ・変数
    for transportation_edge in transportation_list:
        # 部品名
        for product_id in num_product_list:
            # コストを設定
            transportation_edge.calc_cost[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id)] = transportation_edge.cost[product_id]
            # plus,minus
            for sign_id in sign:
                # キャパシティを設定
                transportation_edge.calc_capacity[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id)] = transportation_edge.capacity[product_id]
                # 変数を設定
                transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id)] = model.addVar(name=f'x_transportation_{transportation_edge.source.node_id}_{transportation_edge.target.node_id}_{transportation_edge.function}_{product_id}_{sign_id}', vtype='I')
                # 変数と同じ値をflow_valueに格納して表作成時に用いる
                transportation_edge.flow_value[(transportation_edge.source.name, transportation_edge.target.name, transportation_edge.source.month, product_id, sign_id)] = model.addVar(name=f'x_transportation_{transportation_edge.source.node_id}_{transportation_edge.target.node_id}_{transportation_edge.function}_{product_id}_{sign_id}', vtype='I')
                model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id)] == transportation_edge.flow_value[(transportation_edge.source.name, transportation_edge.target.name, transportation_edge.source.month, product_id, sign_id)])

    # production_listの計算用コスト（長くなるのでコストのみ）
    # 条件を事前に定義
    cost_mapping = {
        "モジュール製作": "モジュール",
        "ハーフボディ1製作": "ハーフボディ1",
        "ハーフボディ3製作": "ハーフボディ3",
        "浮体基礎製作": "浮体基礎",
        "洋上での浮体基礎製作": "浮体基礎",
        "風車組立": "風車",
        "風車設置": "風車（設置済）",
    }
    # コスト
    for production_edge in production_list:
        for product_id in num_product_list:
            # 各function（ex.モジュール製作）のvalue（モジュール製作ならモジュール）をcost_mappingから取得、それをproduct_id（ex.モジュール）と比較
            if cost_mapping.get(production_edge.function) == product_id:
                production_edge.calc_cost[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id)] = production_edge.cost
            else:
                production_edge.calc_cost[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id)] = 0


    # production_listの計算用キャパシティ
    for production_edge in production_list:
        for product_id in num_product_list:
            for sign_id in sign:
                if production_edge.function == "モジュール製作":
                    if (product_id == "鋼材" and sign_id == "plus") or (product_id == "モジュール" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                elif production_edge.function == "ハーフボディ1製作":
                    if (product_id == "モジュール" and sign_id == "plus") or (product_id == "ハーフボディ1" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                elif production_edge.function == "ハーフボディ3製作":
                    if (product_id == "モジュール" and sign_id == "plus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 3 * production_edge.capacity
                    elif (product_id == "ハーフボディ3" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                elif production_edge.function == "浮体基礎製作" or production_edge.function == "洋上での浮体基礎製作":
                    if (product_id == "ハーフボディ1" and sign_id == "plus") or (product_id == "ハーフボディ3" and sign_id == "plus") or (product_id == "浮体基礎" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                elif production_edge.function == "風車組立":
                    if (product_id == "浮体基礎" and sign_id == "plus") or (product_id == "風車" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                elif production_edge.function == "風車設置":
                    if (product_id == "風車" and sign_id == "plus") or (product_id == "風車（設置済）" and sign_id == "minus"):
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = production_edge.capacity
                    else:
                        production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = 0
                # 追加
                else:
                    production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "船舶")] = 0

    # production_listの計算用変数
    for production_edge in production_list:
        for product_id in num_product_list:
            for sign_id in sign:
                production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] = model.addVar(name=f'x_production_{production_edge.source.node_id}_{production_edge.target.node_id}_{production_edge.function}_{product_id}_{sign_id}', vtype='I')

    # storage_listの計算用コスト・キャパシティ・変数
    for storage_edge in storage_list:
        for product_id in num_product_list:
            # 浮体基礎のみコストを設定
            if product_id == "浮体基礎":
                # コストを設定
                storage_edge.calc_cost[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id)] = storage_edge.cost
            else:
                storage_edge.calc_cost[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id)] = 0
            # plus,minus
            for sign_id in sign:
                if product_id == "浮体基礎":
                    # キャパシティを設定
                    storage_edge.calc_capacity[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)] = storage_edge.capacity
                else:
                    storage_edge.calc_capacity[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)] = 0
                # 変数を設定
                storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)] = model.addVar(name=f'x_storage_{storage_edge.source.node_id}_{storage_edge.target.node_id}_{storage_edge.function}_{product_id}_{sign_id}', vtype='I')
                # 変数と同じ値をflow_valueに格納し表作成時に用いる
                storage_edge.flow_value[(storage_edge.source.name, storage_edge.target.name, storage_edge.source.month, product_id, sign_id)] = model.addVar(name=f'x_storage_{storage_edge.source.node_id}_{storage_edge.target.node_id}_{storage_edge.function}_{product_id}_{sign_id}', vtype='I')
                model.addCons(storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)] == storage_edge.flow_value[(storage_edge.source.name, storage_edge.target.name, storage_edge.source.month, product_id, sign_id)])

    # フローがキャパシティを超えないように
    for transportation_edge in transportation_list:
        for product_id in num_product_list:
            for sign_id in sign:
                model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id)] <= transportation_edge.calc_capacity[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id)])

    for production_edge in production_list:
        for product_id in num_product_list:
            for sign_id in sign:
                model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)] <= production_edge.calc_capacity[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id)])

    for storage_edge in storage_list:
        for product_id in num_product_list:
            for sign_id in sign:
                model.addCons(storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)] <= storage_edge.calc_capacity[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id)])

    # 船舶を用いて部材輸送を行うと仮定してコスト計算
    # 輸送
    for transportation_edge in transportation_list:
        for sign_id in sign:
            model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "船舶", sign_id)] >= \
                        1/12 * transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "モジュール", sign_id)] + \
                        1/10 * transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "ハーフボディ1", sign_id)] + \
                        2/5 * transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "ハーフボディ3", sign_id)] + \
                        # ここで1隻の船舶で運べる浮体の数を入力
                        1/2 * transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "浮体基礎", sign_id)] + \
                            transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "鋼材", sign_id)] + \
                            transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "風車", sign_id)])
    # production,storageでは、船舶のフローは0
    for production_edge in production_list:
        for product_id in num_product_list:
            for sign_id in sign:
                model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "船舶", sign_id)] == 0)

    for storage_edge in storage_list:
        for product_id in num_product_list:
            model.addCons(storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, "船舶", "minus")] == 0)

    ## 修正ポイント
    for transportation_edge in transportation_list:
        if transportation_edge.target.node_id == "(能代沖6_10000月)" and transportation_edge.function == "輸送":
            model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "船舶", "minus")] == 0)


    # sign_idのplusとminusでflowが不変
    # 輸送
    for transportation_edge in transportation_list:
        for product_id in num_product_list:
            model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "plus")] == transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "minus")])
            
    # 仮置
    for storage_edge in storage_list:
        for product_id in num_product_list:
            model.addCons(storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, "plus")] == storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, "minus")])

    ## 修正ポイント
    for transportation_edge in transportation_list:
        if transportation_edge.target.node_id == "(能代沖_10000月)" and transportation_edge.function == "輸送":
            model.addCons(transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, "船舶", "minus")] == 0)





    # B行列
    for production_edge in production_list:
        # モジュール製作を想定
        model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "鋼材", "plus")] == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "minus")])
        # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "鋼材", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "鋼材", "minus")])

        # ハーフボディ1製作を想定（ここだけは場合分け必要）
        if production_edge.function == "ハーフボディ1製作":
            model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "plus")] == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ1", "minus")])
            # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "minus")])

        # ハーフボディ3製作を想定（ここだけは場合分け必要）
        if production_edge.function == "ハーフボディ3製作":
            model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "plus")] == 3 * production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ3", "minus")])
            # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "モジュール", "minus")])

        # 浮体基礎製作、洋上での浮体基礎製作を想定
        # ハーフボディ1とハーフボディ3の流出量が等しい（変換前）
        model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ1", "plus")] == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ3", "plus")])
        # 変換前と変換後の部材比率
        model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ1", "plus")] / 2 + production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ3", "plus")] / 2 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "浮体基礎", "minus")])
        # 変換後のハーフボディ1とハーフボディ3の部材は0
        # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ1", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ1", "minus")])
        # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ3", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "ハーフボディ3", "minus")])

        # 風車組立を想定
        model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "浮体基礎", "plus")] == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車", "minus")])
        # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "浮体基礎", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "浮体基礎", "minus")])

        # 風車設置を想定
        model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車", "plus")] == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車（設置済）", "minus")])
        # model.addCons(production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車", "plus")] * 0 == production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車", "minus")])





    # Mass Balance
    # そのノードでの流出量 - そのノードでの流入量 = そのノードでの生産量
    # node_id × product_idごとに計算
    for node in node_list:
        for product_id in num_product_list[:-1]:
            # print(f'NODE_ID: {node.node_id}, PRODUCT_ID: {product_id}')

            # 各node_id,productから出るエッジを取得
            plus_edge = [transportation_edge.flow[transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "plus"] for transportation_edge in transportation_list if transportation_edge.source.node_id == node.node_id] + [production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, "plus"] for production_edge in production_list if production_edge.source.node_id == node.node_id] + [storage_edge.flow[storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, "plus"] for storage_edge in storage_list if storage_edge.source.node_id == node.node_id]
            # print(f"出力フロー (x_plus): {plus_edge}")

            # 各node_id,productに入るエッジを取得
            minus_edge = [transportation_edge.flow[transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "minus"] for transportation_edge in transportation_list if transportation_edge.target.node_id == node.node_id] + [production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, "minus"] for production_edge in production_list if production_edge.target.node_id == node.node_id] + [storage_edge.flow[storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, "minus"] for storage_edge in storage_list if storage_edge.target.node_id == node.node_id]
            # print(f"入力フロー (x_minus): {minus_edge}")
            
            # 制約をかける
            # そのノードでの流出量 - そのノードでの流入量 <= そのノードでの生産量
            model.addCons((quicksum(plus_edge) - quicksum(minus_edge)) <= node.calc_supply_demand[node.node_id, product_id])

    # transportation_listのコストを計算
    transportation_cost = 0
    for transportation_edge in transportation_list:
        for product_id in num_product_list:
            transportation_cost += transportation_edge.calc_cost[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id)] * transportation_edge.flow[(transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "minus")]

    # production_listのコストを計算
    production_cost = 0
    for production_edge in production_list:
        for product_id in num_product_list:
            production_cost += production_edge.calc_cost[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id)] * production_edge.flow[(production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, "minus")]

    # storage_listのコストを計算
    storage_cost = 0
    for storage_edge in storage_list:
        for product_id in num_product_list:
            storage_cost += storage_edge.calc_cost[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id)] * storage_edge.flow[(storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, "minus")]

    # コスト最小
    model.setObjective(transportation_cost + production_cost + storage_cost, sense='minimize')

    # 最適化
    model.hideOutput()
    model.optimize()

    # フラット辞書
    transportation_results = {}
    production_results = {}
    storage_results = {}

    if model.getStatus() == "optimal":
        print("最適化が完了しました。")
        # 輸送エッジ
        for transportation_edge in transportation_list:
            for product_id in num_product_list:
                for sign_id in sign:
                    var_name = f'transportation_{transportation_edge.source.node_id}_{transportation_edge.target.node_id}_{transportation_edge.function}_{product_id}_{sign_id}'
                    var = transportation_edge.flow[transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, sign_id]
                    value = model.getVal(var)
                    if value >= 0.1 and sign_id == "minus" and product_id != "船舶":
                        transportation_results[var_name] = value

        # 製作エッジ
        for production_edge in production_list:
            for product_id in num_product_list:
                for sign_id in sign:
                    var_name = f'production_{production_edge.source.node_id}_{production_edge.target.node_id}_{production_edge.function}_{product_id}_{sign_id}'
                    var = production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, product_id, sign_id]
                    value = model.getVal(var)
                    if value >= 0.1 and sign_id == "minus":
                        production_results[var_name] = value

        # 仮置エッジ
        for storage_edge in storage_list:
            for product_id in num_product_list:
                for sign_id in sign:
                    var_name = f'storage_{storage_edge.source.node_id}_{storage_edge.target.node_id}_{storage_edge.function}_{product_id}_{sign_id}'
                    var = storage_edge.flow[storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, product_id, sign_id]
                    value = model.getVal(var)
                    if value >= 0.1 and sign_id == "minus":
                        storage_results[var_name] = value


        return node_list, \
               transportation_list, \
               production_list, \
               storage_list, \
               model

# 描画関数
def build_maps(node_list, transportation_list, production_list, storage_list, model):
    # 各月の地図とnetworkx結果を入れるファイル作成
    maps_by_month = {}
    # 月毎にHTMLファイルを作成
    for month in layer_network_list:
        # NetworkX でネットワーク図作成
        G = nx.DiGraph()
        # -------------------------------------------------
        # 1) ノード情報追加
        for node in node_list:
            if node.month == month:
                G.add_node(node.name)
                G.nodes[node.name]["pos"] = [node.lat, node.lon]
                # ノード名、
                G.add_node(node.name)
                # 色々な属性を追加
                # 緯度経度
                G.nodes[node.name]["pos"] = [node.lat, node.lon]
                # モジュール製作〜浮体基礎製作
                G.nodes[node.name]["浮体生産量"] = int(model.getVal(quicksum(production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "浮体基礎", "minus"] for production_edge in production_list if production_edge.source.node_id == node.node_id and (production_edge.function == "浮体基礎製作" or production_edge.function == "洋上での浮体基礎製作"))))
                # 仮置数
                G.nodes[node.name]["仮置数"] = int(model.getVal(quicksum(storage_edge.flow[storage_edge.source.node_id, storage_edge.target.node_id, storage_edge.function, "浮体基礎", "minus"] for storage_edge in storage_list if storage_edge.source.node_id == node.node_id)))
                # 風車組立数
                G.nodes[node.name]["風車組立数"] = int(model.getVal(quicksum(production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車", "minus"] for production_edge in production_list if production_edge.source.node_id == node.node_id and production_edge.function == "風車組立")))
                # 風車設置数
                G.nodes[node.name]["風車設置数"] = int(model.getVal(quicksum(production_edge.flow[production_edge.source.node_id, production_edge.target.node_id, production_edge.function, "風車（設置済）", "minus"] for production_edge in production_list if production_edge.source.node_id == node.node_id and production_edge.function == "風車設置")))
            else:
                pass
        # -------------------------------------------------
        # 2) エッジ情報追加
        # エッジリストから情報をとる（各月の）
        for edge in transportation_list:
            if edge.month == month:
                # エッジの始点、終点
                G.add_edge(edge.source.name, edge.target.name)
                # リンクに各部品がどれだけ輸送されたかの属性を追加
                for product_id in num_product_list:
                    G.edges[edge.source.name, edge.target.name][product_id] = int(model.getVal(quicksum(transportation_edge.flow[transportation_edge.source.node_id, transportation_edge.target.node_id, transportation_edge.function, product_id, "minus"] for transportation_edge in transportation_list if transportation_edge.source.node_id == edge.source.node_id and transportation_edge.target.node_id == edge.target.node_id)))
            else:
                pass
        # -------------------------------------------------
        # 3) Folium 地図を作成
        m = folium.Map(location=[35.681236, 139.767125], zoom_start=6, tiles='CartoDB Positron', attr='CartoDB Positron')
        # -------------------------------------------------
        # 4) エッジ情報の描画 (常時表示ツールチップ)
        for u, v, data in G.edges(data=True):
            # 輸送量がすべて0なら描画しない
            if all(data.get(product_id, 0) == 0 for product_id in num_product_list):
                continue

            # エッジの描画（輸送された時のみ）
            edge_polyline = folium.PolyLine(
                locations=[G.nodes[u]["pos"], G.nodes[v]["pos"]],
                color='blue',
                weight=3
            )
            # 常時表示のTooltipを追加
            edge_polyline.add_to(m)
        # -------------------------------------------------
        # 5) ノード情報の描画 (CircleMarker + Marker)
        for node_name in G.nodes():
            lat, lon = G.nodes[node_name]['pos']

            # ① 円の描画
            circle = folium.CircleMarker(
                location=[lat, lon],
                radius=15,
                color=None,
                fill=True,
                fill_color='red',
                fill_opacity=1,
                tooltip=node_name
            )
            circle.add_to(m)


            # ② テキストの描画
            display_name = node_name[:-1] # 最後の1文字を表示させない
            char_size = 10
            text_len = len(display_name)
            icon_w = char_size * text_len   # 幅
            icon_h = char_size * 1.2        # 高さ（行間考慮で少し増やす）
            
            marker = folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                icon_size=(icon_w, icon_h),
                icon_anchor=(icon_w/2, icon_h/2),
                html=f"""
                <div style="
                    width: {icon_w}px;
                    height: {icon_h}px;
                    line-height: {icon_h}px;
                    text-align: center;
                    font-family: monospace;
                    font-size: {char_size}px;
                    font-weight: bold;
                    color: white;
                    ">
                    {display_name}
                </div>
                """
            )
            )
            marker.add_to(m)
            # ノードのみ時に触れた際にも情報表示
            Tooltip(node_name, 
                    permanent=False,   # ホバー時のみ表示
                    sticky=True       # マウスに追随
                ).add_to(marker) 
           
        # -------------------------------------------------
        # 6) 不要な枠線の除去 & フォントサイズ修正 (任意)
        css = """
        <style>
            .leaflet-interactive:focus {
                outline: none !important;
            }
            .leaflet-tooltip {
                font-size: 10px !important;
                font-weight: bold;
            }
        </style>
        """
        m.get_root().html.add_child(folium.Element(css))

        # 生成したマップを HTML 文字列として取得
        maps_by_month[month] = m._repr_html_()

    return maps_by_month

"""
if __name__ == "__main__":
    # ここで直接ファイルパスを指定して呼び出し
    transportation_results, production_results, storage_results, node_list, transportation_list, production_list, storage_list, model  = optimize("/Users/shimozawatakahiro/Documents/プログラム/input_node_描画用.csv","/Users/shimozawatakahiro/Documents/プログラム/input_edge_シンポジウムCase3.csv")
    print("=== Transportation Results ===")
    for k, v in transportation_results.items():
        print(f"{k}: {v}")

    print("\n=== Production Results ===")
    for k, v in production_results.items():
        print(f"{k}: {v}")

    print("\n=== Storage Results ===")
    for k, v in storage_results.items():
        print(f"{k}: {v}")
    
    build_maps(node_list, transportation_list, production_list, storage_list, model)
"""