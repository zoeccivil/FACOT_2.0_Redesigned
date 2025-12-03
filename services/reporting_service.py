"""
Servicio de Reportes para FACOT.

Proporciona funciones para generar reportes de ventas y clientes,
con soporte para agregación por período, exportación a CSV y más.
"""

from __future__ import annotations
import csv
import os
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Literal
from collections import defaultdict


GroupByType = Literal["day", "month", "product", "client"]


class ReportingService:
    """
    Servicio para generar reportes de ventas y clientes.
    
    Soporta:
    - Reporte de ventas por período (agrupado por día, mes o producto)
    - Reporte de clientes (totales por cliente)
    - Exportación a CSV
    """
    
    def __init__(self, data_access):
        """
        Inicializa el servicio de reportes.
        
        Args:
            data_access: Instancia de data_access (Firebase o SQLite)
        """
        self.data_access = data_access
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parsea una fecha desde string."""
        if not date_str:
            return None
        
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
    
    def _get_invoices_in_period(
        self, 
        start_date: date, 
        end_date: date, 
        company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene facturas en un período.
        
        Args:
            start_date: Fecha de inicio
            end_date: Fecha de fin
            company_id: ID de empresa (opcional)
        
        Returns:
            Lista de facturas filtradas
        """
        # Obtener todas las facturas
        if hasattr(self.data_access, 'get_invoices'):
            invoices = self.data_access.get_invoices(company_id=company_id, limit=10000)
        elif hasattr(self.data_access, 'get_facturas'):
            invoices = self.data_access.get_facturas(company_id) if company_id else []
        else:
            invoices = []
        
        # Filtrar por fecha
        filtered = []
        for inv in invoices:
            inv_date_str = inv.get('invoice_date') or inv.get('date') or ''
            inv_date = self._parse_date(inv_date_str)
            
            if inv_date and start_date <= inv_date <= end_date:
                filtered.append(inv)
        
        return filtered
    
    def sales_by_period(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[int] = None,
        group_by: GroupByType = "day"
    ) -> List[Dict[str, Any]]:
        """
        Genera reporte de ventas por período.
        
        Args:
            start_date: Fecha de inicio
            end_date: Fecha de fin
            company_id: ID de empresa (opcional)
            group_by: Tipo de agrupación ("day", "month", "product")
        
        Returns:
            Lista de registros agregados con campos:
            - key: Clave de agrupación
            - count_invoices: Número de facturas
            - total_amount: Monto total
            - avg_amount: Monto promedio
            - first_date: Primera fecha
            - last_date: Última fecha
        """
        invoices = self._get_invoices_in_period(start_date, end_date, company_id)
        
        if not invoices:
            return []
        
        # Agrupar según el tipo
        groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count_invoices": 0,
            "total_amount": 0.0,
            "dates": []
        })
        
        for inv in invoices:
            inv_date_str = inv.get('invoice_date') or inv.get('date') or ''
            inv_date = self._parse_date(inv_date_str)
            amount = float(inv.get('total_amount') or inv.get('total') or 0)
            
            # Determinar la clave de agrupación
            if group_by == "day":
                key = inv_date.isoformat() if inv_date else "unknown"
            elif group_by == "month":
                key = inv_date.strftime("%Y-%m") if inv_date else "unknown"
            elif group_by == "product":
                # Agrupar por productos (requiere items)
                items = inv.get('items') or []
                if items:
                    for item in items:
                        product_key = item.get('description') or item.get('code') or 'Sin Producto'
                        item_amount = float(item.get('quantity', 1)) * float(item.get('unit_price', 0))
                        groups[product_key]["count_invoices"] += 1
                        groups[product_key]["total_amount"] += item_amount
                        if inv_date:
                            groups[product_key]["dates"].append(inv_date)
                    continue
                else:
                    key = "Sin Productos"
            else:
                key = inv_date.isoformat() if inv_date else "unknown"
            
            groups[key]["count_invoices"] += 1
            groups[key]["total_amount"] += amount
            if inv_date:
                groups[key]["dates"].append(inv_date)
        
        # Convertir a lista de resultados
        results = []
        for key, data in groups.items():
            dates = data["dates"]
            count = data["count_invoices"]
            total = data["total_amount"]
            
            results.append({
                "key": key,
                "count_invoices": count,
                "total_amount": round(total, 2),
                "avg_amount": round(total / count, 2) if count > 0 else 0,
                "first_date": min(dates).isoformat() if dates else None,
                "last_date": max(dates).isoformat() if dates else None,
            })
        
        # Ordenar por clave
        results.sort(key=lambda x: x["key"])
        
        return results
    
    def clients_by_period(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Genera reporte por cliente.
        
        Args:
            start_date: Fecha de inicio
            end_date: Fecha de fin
            company_id: ID de empresa (opcional)
        
        Returns:
            Lista de registros por cliente con campos:
            - client_id: ID o RNC del cliente
            - client_name: Nombre del cliente
            - invoices_count: Número de facturas
            - total_amount: Monto total
            - last_invoice_date: Fecha de última factura
        """
        invoices = self._get_invoices_in_period(start_date, end_date, company_id)
        
        if not invoices:
            return []
        
        # Agrupar por cliente
        clients: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "client_name": "",
            "invoices_count": 0,
            "total_amount": 0.0,
            "dates": []
        })
        
        for inv in invoices:
            # Identificar cliente por RNC o nombre
            client_id = (
                inv.get('client_rnc') or 
                inv.get('rnc') or 
                inv.get('third_party_rnc') or
                inv.get('client_name') or
                inv.get('third_party_name') or
                "Sin Cliente"
            )
            client_name = (
                inv.get('client_name') or 
                inv.get('third_party_name') or 
                client_id
            )
            
            inv_date_str = inv.get('invoice_date') or inv.get('date') or ''
            inv_date = self._parse_date(inv_date_str)
            amount = float(inv.get('total_amount') or inv.get('total') or 0)
            
            clients[client_id]["client_name"] = client_name
            clients[client_id]["invoices_count"] += 1
            clients[client_id]["total_amount"] += amount
            if inv_date:
                clients[client_id]["dates"].append(inv_date)
        
        # Convertir a lista de resultados
        results = []
        for client_id, data in clients.items():
            dates = data["dates"]
            
            results.append({
                "client_id": client_id,
                "client_name": data["client_name"],
                "invoices_count": data["invoices_count"],
                "total_amount": round(data["total_amount"], 2),
                "last_invoice_date": max(dates).isoformat() if dates else None,
            })
        
        # Ordenar por monto total descendente
        results.sort(key=lambda x: x["total_amount"], reverse=True)
        
        return results


def export_sales_csv(dataset: List[Dict[str, Any]], file_path: str) -> bool:
    """
    Exporta reporte de ventas a CSV.
    
    Args:
        dataset: Lista de registros del reporte
        file_path: Ruta del archivo CSV
    
    Returns:
        True si se exportó correctamente
    """
    try:
        headers = ["key", "count_invoices", "total_amount", "avg_amount", "first_date", "last_date"]
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for row in dataset:
                writer.writerow({h: row.get(h, '') for h in headers})
        
        return True
    except Exception as e:
        print(f"[REPORTS] Error exportando CSV de ventas: {e}")
        return False


def export_clients_csv(dataset: List[Dict[str, Any]], file_path: str) -> bool:
    """
    Exporta reporte de clientes a CSV.
    
    Args:
        dataset: Lista de registros del reporte
        file_path: Ruta del archivo CSV
    
    Returns:
        True si se exportó correctamente
    """
    try:
        headers = ["client_id", "client_name", "invoices_count", "total_amount", "last_invoice_date"]
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for row in dataset:
                writer.writerow({h: row.get(h, '') for h in headers})
        
        return True
    except Exception as e:
        print(f"[REPORTS] Error exportando CSV de clientes: {e}")
        return False


def export_report_html(
    dataset: List[Dict[str, Any]], 
    title: str,
    headers: List[str],
    file_path: str
) -> bool:
    """
    Exporta reporte a HTML (para preview o conversión a PDF).
    
    Args:
        dataset: Lista de registros del reporte
        title: Título del reporte
        headers: Lista de encabezados a mostrar
        file_path: Ruta del archivo HTML
    
    Returns:
        True si se exportó correctamente
    """
    try:
        html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #4a90d9; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        tr:hover {{ background-color: #f1f1f1; }}
        .total-row {{ font-weight: bold; background-color: #e0e0e0; }}
        .footer {{ margin-top: 20px; text-align: center; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <table>
        <thead>
            <tr>
                {''.join(f'<th>{h}</th>' for h in headers)}
            </tr>
        </thead>
        <tbody>
"""
        
        for row in dataset:
            html_content += "            <tr>\n"
            for h in headers:
                value = row.get(h, '')
                if isinstance(value, float):
                    value = f"{value:,.2f}"
                html_content += f"                <td>{value}</td>\n"
            html_content += "            </tr>\n"
        
        html_content += """
        </tbody>
    </table>
    
    <div class="footer">
        <p>FACOT 2.0 - Sistema de Facturación</p>
    </div>
</body>
</html>
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return True
    except Exception as e:
        print(f"[REPORTS] Error exportando HTML: {e}")
        return False


# Instancia global (opcional)
_reporting_service: Optional[ReportingService] = None


def get_reporting_service(data_access=None) -> Optional[ReportingService]:
    """
    Obtiene o crea una instancia del servicio de reportes.
    
    Args:
        data_access: Instancia de data_access (requerido en primera llamada)
    
    Returns:
        Instancia de ReportingService o None si no hay data_access
    """
    global _reporting_service
    
    if data_access:
        _reporting_service = ReportingService(data_access)
    
    return _reporting_service
