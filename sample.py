# sample.py
from flask import Flask, request, render_template, redirect, url_for
import io
from calc import build_maps, optimize, num_product_list, sign

app = Flask(__name__)
app.secret_key = '十分ランダムな文字列'

# グローバルキャッシュ
GLOBAL_CACHE = {
    'maps_by_month': None,
    'node_list': None,
    'active_month': None,
    'production_results': None,
    'storage_results': None
}

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/show', methods=['GET', 'POST'])
def show():
    if request.method == 'POST':
        # POST: ファイル受け取り → 最適化 → キャッシュ
        node_stream = io.TextIOWrapper(request.files['node_file'].stream, encoding='utf-8-sig')
        edge_stream = io.TextIOWrapper(request.files['edge_file'].stream, encoding='utf-8-sig')

        node_list, transportation_list, production_list, storage_list, model = optimize(node_stream, edge_stream)

        # 生産結果表示プログラム
        production_results = {}
        for pe in production_list:
            month = pe.source.month
            node = pe.source.name
            # key=ノード&月のセット
            key = (month, node)
            # このキーのリストがなければ新規作成
            production_results.setdefault(key, [])
            for product_id in num_product_list:
                for sign_id in sign:
                    var = pe.flow[
                        (pe.source.node_id,
                        pe.target.node_id,
                        pe.function,
                        product_id,
                        sign_id)
                    ]
                    val = model.getVal(var)
                    # minus のフロー（＝生産量の実数値）だけ取る
                    if sign_id == 'minus' and val >= 0.1:
                        # value=値
                        production_results[key].append(
                            (pe.function, val)
                        )
        
        # 仮置結果表示プログラム
        storage_results = {}
        for pe in storage_list:            
            month = pe.source.month
            node = pe.source.name
            # key=ノード&月のセット
            key = (month, node)
            # このキーのリストがなければ新規作成
            storage_results.setdefault(key, [])
            for product_id in num_product_list:
                for sign_id in sign:
                    var = pe.flow[
                        (pe.source.node_id,
                        pe.target.node_id,
                        pe.function,
                        product_id,
                        sign_id)
                    ]
                    val = model.getVal(var)
                    # minus のフロー（＝生産量の実数値）だけ取る
                    if sign_id == 'minus' and val >= 0.1:
                        # value=値
                        storage_results[key].append(
                            (pe.function, val)
                        )


        maps_by_month = build_maps(node_list, transportation_list, production_list, storage_list, model)

        # グローバルキャッシュに保存
        GLOBAL_CACHE['maps_by_month'] = maps_by_month
        GLOBAL_CACHE['node_list'] = node_list
        GLOBAL_CACHE['production_results'] = production_results
        GLOBAL_CACHE['storage_results'] = storage_results
        # 初期表示月を先頭に
        GLOBAL_CACHE['active_month'] = next(iter(maps_by_month.keys()))
        return redirect(url_for('show'))

    # GET: キャッシュから読み出し → タブ切り替えの ?month=XX を受け取って active_month 更新
    maps_by_month = GLOBAL_CACHE['maps_by_month']
    node_list      = GLOBAL_CACHE['node_list'] or []
    production_results = GLOBAL_CACHE['production_results'] or {}
    storage_results = GLOBAL_CACHE['storage_results'] or {}
    active_month   = request.args.get('month', GLOBAL_CACHE['active_month'])


    return render_template(
        'index.html',
        maps_by_month=maps_by_month,
        node_list=node_list,
        production_results = production_results,
        storage_results = storage_results,
        active_month=active_month
    )

if __name__ == '__main__':
    app.run(debug=True, port=8000)