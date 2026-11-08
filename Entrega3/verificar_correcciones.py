"""Pruebas de casos temporales y ejecución del notebook, con salida conservada si falla."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from analisis_correcciones import auditar_alarmas, emparejar_episodios, resumen_temporal

HERE = Path(__file__).resolve().parent


class CasosTemporales(unittest.TestCase):
    def datos(self, vueltas, pits, piloto=1):
        return pd.DataFrame({'session_key': 10, 'driver_number': piloto,
                             'lap_number': vueltas, 'pit_stop': [v in pits for v in vueltas]})

    def test_anticipacion_y_no_aviso_posterior(self):
        t, ep, reales = auditar_alarmas(self.datos(range(1, 9), [5]), [0, 0, 1, 1, 0, 1, 0, 1], .5)
        self.assertEqual(t.loc[2, 'distancia_proxima_parada'], 2)
        self.assertEqual(t.loc[5, 'desde_parada_anterior'], 1)
        self.assertTrue(np.isnan(t.loc[5, 'distancia_proxima_parada']))
        self.assertEqual(emparejar_episodios(ep, reales, 0), 0)
        self.assertEqual(emparejar_episodios(ep, reales, 1), 1)
        self.assertEqual(emparejar_episodios(ep, reales, 3), 1)

    def test_varias_alarmas_no_multiplican_parada(self):
        t, ep, reales = auditar_alarmas(self.datos(range(1, 7), [5]), [0, 1, 0, 1, 1, 0], .5)
        r = resumen_temporal(t, ep, reales).set_index('tolerancia')
        self.assertEqual(r.loc[3, 'episodios_emparejados'], 1)
        self.assertEqual(r.loc[3, 'precision_episodios'], .5)
        self.assertEqual(r.loc[3, 'cobertura_paradas'], 1)

    def test_no_cruza_piloto_y_corta_en_parada(self):
        datos = pd.concat([self.datos([1, 2, 3, 4], [2, 4]), self.datos([1, 2, 3, 4], [], 2)])
        t, ep, reales = auditar_alarmas(datos, np.ones(8), .5)
        self.assertEqual(len(ep), 3)
        self.assertEqual(emparejar_episodios(ep, reales, 3), 2)
        self.assertTrue(t.loc[t.driver_number.eq(2), 'distancia_proxima_parada'].isna().all())

    def test_sin_alarmas_y_sin_paradas(self):
        t, ep, reales = auditar_alarmas(self.datos([1, 2, 4], []), [0, 0, 0], .5)
        self.assertEqual(len(ep), 0)
        self.assertTrue(resumen_temporal(t, ep, reales).precision_episodios.isna().all())
        _, ep, _ = auditar_alarmas(self.datos([1, 2, 4], []), [1, 1, 1], .5)
        self.assertEqual(len(ep), 2)

    def test_rechaza_duplicados(self):
        with self.assertRaises(ValueError):
            auditar_alarmas(self.datos([1, 1], []), [0, 1], .5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ejecutar', action='store_true')
    args = parser.parse_args()
    resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CasosTemporales))
    if not resultado.wasSuccessful():
        raise SystemExit(1)
    import nbformat
    ruta = HERE / 'Entrega3_F1_v7_correcciones.ipynb'
    nb = nbformat.read(ruta, as_version=4)
    nbformat.validate(nb)
    for i, c in enumerate(nb.cells):
        if c.cell_type == 'code':
            ast.parse(c.source, filename=f'celda_{i}')
    print('Estructura y sintaxis válidas', flush=True)
    if args.ejecutar:
        from nbclient import NotebookClient
        from jupyter_client.kernelspec import KernelSpecManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / 'correcciones'
            spec.mkdir()
            (spec / 'kernel.json').write_text(json.dumps({'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                'display_name': 'Correcciones local', 'language': 'python'}), encoding='utf-8')
            ksm = KernelSpecManager(kernel_dirs=[tmp])
            from jupyter_client import KernelManager
            km = KernelManager(kernel_name='correcciones', kernel_spec_manager=ksm)
            cliente = NotebookClient(nb, km=km, timeout=1800, resources={'metadata': {'path': str(HERE)}})
            cliente.on_cell_start = lambda cell, cell_index: print(f'Ejecutando celda {cell_index}: {cell.source.splitlines()[0][:90]}', flush=True)
            try:
                cliente.execute()
            finally:
                nbformat.write(nb, ruta)
            print('Notebook ejecutado y guardado', flush=True)


if __name__ == '__main__':
    main()
