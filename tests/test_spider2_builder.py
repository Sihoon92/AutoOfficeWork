"""
Spider2Builder 단위 테스트

APC QueryBuilder(tests/test_builder.py)와 동일한 패턴으로 작성.
실제 DB 없이 Spider2QuerySpec → SQL 문자열만 검증한다.
"""
import pytest

from spider2.builder import Spider2Builder, Spider2BuilderError
from spider2.schema import (
    JoinClause,
    OrderByClause,
    Spider2QuerySpec,
    WhereCondition,
)


# ── 기본 SELECT ───────────────────────────────────────
class TestSelectClause:
    def test_select_all(self):
        spec = Spider2QuerySpec(from_table="employees")
        sql = Spider2Builder(spec).build()
        assert "SELECT *" in sql
        assert "FROM employees" in sql

    def test_select_columns(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            select_columns=["name", "salary"],
        )
        sql = Spider2Builder(spec).build()
        assert "SELECT name, salary" in sql

    def test_select_distinct(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            select_columns=["dept_id"],
            distinct=True,
        )
        sql = Spider2Builder(spec).build()
        assert "SELECT DISTINCT dept_id" in sql

    def test_select_with_aggregation(self):
        spec = Spider2QuerySpec(
            from_table="orders",
            select_columns=["customer_id", "COUNT(*) AS cnt"],
        )
        sql = Spider2Builder(spec).build()
        assert "COUNT(*) AS cnt" in sql

    def test_from_with_alias(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            from_alias="e",
            select_columns=["e.name"],
        )
        sql = Spider2Builder(spec).build()
        assert "FROM employees AS e" in sql


# ── WHERE 조건 ────────────────────────────────────────
class TestWhereClause:
    def test_single_equal(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="dept_id", operator="=", value=3)
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "WHERE dept_id = 3" in sql

    def test_string_equal(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="status", operator="=", value="active")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "WHERE status = 'active'" in sql

    def test_greater_than(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="salary", operator=">", value=50000)
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "salary > 50000" in sql

    def test_like_operator(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="name", operator="LIKE", value="%Kim%")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "name LIKE '%Kim%'" in sql

    def test_in_operator(self):
        spec = Spider2QuerySpec(
            from_table="orders",
            where_conditions=[
                WhereCondition(column="status", operator="IN", value=["paid", "shipped"])
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "status IN ('paid', 'shipped')" in sql

    def test_is_null(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="end_date", operator="IS NULL")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "end_date IS NULL" in sql

    def test_between(self):
        spec = Spider2QuerySpec(
            from_table="sales",
            where_conditions=[
                WhereCondition(column="amount", operator="BETWEEN", value=[100, 500])
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "amount BETWEEN 100 AND 500" in sql

    def test_multiple_and_conditions(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="dept_id", operator="=", value=1),
                WhereCondition(column="salary", operator=">=", value=40000),
            ],
            where_logic="AND",
        )
        sql = Spider2Builder(spec).build()
        assert "dept_id = 1" in sql
        assert "salary >= 40000" in sql
        assert " AND " in sql

    def test_or_conditions(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            where_conditions=[
                WhereCondition(column="dept_id", operator="=", value=1),
                WhereCondition(column="dept_id", operator="=", value=2),
            ],
            where_logic="OR",
        )
        sql = Spider2Builder(spec).build()
        assert " OR " in sql

    def test_string_escaping(self):
        """작은따옴표가 포함된 값 이스케이프 테스트"""
        spec = Spider2QuerySpec(
            from_table="products",
            where_conditions=[
                WhereCondition(column="name", operator="=", value="O'Brien")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "name = 'O''Brien'" in sql

    def test_between_wrong_value_raises(self):
        spec = Spider2QuerySpec(
            from_table="t",
            where_conditions=[
                WhereCondition(column="x", operator="BETWEEN", value=100)  # 리스트 아님
            ],
        )
        with pytest.raises(Spider2BuilderError):
            Spider2Builder(spec).build()

    def test_in_wrong_value_raises(self):
        spec = Spider2QuerySpec(
            from_table="t",
            where_conditions=[
                WhereCondition(column="x", operator="IN", value="not_a_list")
            ],
        )
        with pytest.raises(Spider2BuilderError):
            Spider2Builder(spec).build()


# ── JOIN ─────────────────────────────────────────────
class TestJoinClause:
    def test_inner_join(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            from_alias="e",
            select_columns=["e.name", "d.dept_name"],
            joins=[
                JoinClause(table="departments", alias="d", on="e.dept_id = d.id")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "INNER JOIN departments AS d ON e.dept_id = d.id" in sql

    def test_left_join(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            from_alias="e",
            select_columns=["e.name", "p.project_name"],
            joins=[
                JoinClause(
                    table="projects", alias="p",
                    on="e.project_id = p.id",
                    join_type="LEFT",
                )
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "LEFT JOIN" in sql

    def test_multiple_joins(self):
        spec = Spider2QuerySpec(
            from_table="orders",
            from_alias="o",
            select_columns=["o.id", "c.name", "p.product_name"],
            joins=[
                JoinClause(table="customers", alias="c", on="o.customer_id = c.id"),
                JoinClause(table="products", alias="p", on="o.product_id = p.id"),
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "INNER JOIN customers AS c" in sql
        assert "INNER JOIN products AS p" in sql

    def test_join_without_alias(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            select_columns=["employees.name", "departments.name"],
            joins=[
                JoinClause(table="departments", on="employees.dept_id = departments.id")
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "INNER JOIN departments ON" in sql
        assert "AS" not in sql.split("JOIN")[1].split("ON")[0]


# ── GROUP BY / HAVING ──────────────────────────────────
class TestGroupByHaving:
    def test_group_by(self):
        spec = Spider2QuerySpec(
            from_table="orders",
            select_columns=["customer_id", "COUNT(*) AS cnt"],
            group_by=["customer_id"],
        )
        sql = Spider2Builder(spec).build()
        assert "GROUP BY customer_id" in sql

    def test_group_by_multiple(self):
        spec = Spider2QuerySpec(
            from_table="sales",
            select_columns=["year", "month", "SUM(amount)"],
            group_by=["year", "month"],
        )
        sql = Spider2Builder(spec).build()
        assert "GROUP BY year, month" in sql

    def test_having(self):
        spec = Spider2QuerySpec(
            from_table="orders",
            select_columns=["customer_id", "COUNT(*) AS cnt"],
            group_by=["customer_id"],
            having="COUNT(*) > 5",
        )
        sql = Spider2Builder(spec).build()
        assert "HAVING COUNT(*) > 5" in sql


# ── ORDER BY / LIMIT ──────────────────────────────────
class TestOrderByLimit:
    def test_order_by_asc(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            order_by=[OrderByClause(column="salary", direction="ASC")],
        )
        sql = Spider2Builder(spec).build()
        assert "ORDER BY salary ASC" in sql

    def test_order_by_desc(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            order_by=[OrderByClause(column="hire_date", direction="DESC")],
        )
        sql = Spider2Builder(spec).build()
        assert "ORDER BY hire_date DESC" in sql

    def test_multiple_order_by(self):
        spec = Spider2QuerySpec(
            from_table="employees",
            order_by=[
                OrderByClause(column="dept_id", direction="ASC"),
                OrderByClause(column="salary", direction="DESC"),
            ],
        )
        sql = Spider2Builder(spec).build()
        assert "ORDER BY dept_id ASC, salary DESC" in sql

    def test_limit(self):
        spec = Spider2QuerySpec(from_table="employees", limit=10)
        sql = Spider2Builder(spec).build()
        assert "LIMIT 10" in sql


# ── 복합 시나리오 ──────────────────────────────────────
class TestComplexScenarios:
    def test_full_query(self):
        """JOIN + WHERE + GROUP BY + HAVING + ORDER BY + LIMIT 전체 조합"""
        spec = Spider2QuerySpec(
            from_table="orders",
            from_alias="o",
            select_columns=["c.name", "COUNT(*) AS order_cnt", "SUM(o.amount) AS total"],
            joins=[JoinClause(table="customers", alias="c", on="o.customer_id = c.id")],
            where_conditions=[
                WhereCondition(column="o.status", operator="=", value="completed")
            ],
            group_by=["c.name"],
            having="COUNT(*) >= 2",
            order_by=[OrderByClause(column="total", direction="DESC")],
            limit=5,
        )
        sql = Spider2Builder(spec).build()

        assert "SELECT c.name, COUNT(*) AS order_cnt, SUM(o.amount) AS total" in sql
        assert "FROM orders AS o" in sql
        assert "INNER JOIN customers AS c ON o.customer_id = c.id" in sql
        assert "WHERE o.status = 'completed'" in sql
        assert "GROUP BY c.name" in sql
        assert "HAVING COUNT(*) >= 2" in sql
        assert "ORDER BY total DESC" in sql
        assert "LIMIT 5" in sql

    def test_sql_order(self):
        """SQL 절 순서가 올바른지 확인: SELECT → FROM → JOIN → WHERE → GROUP → HAVING → ORDER → LIMIT"""
        spec = Spider2QuerySpec(
            from_table="t",
            select_columns=["a", "COUNT(*)"],
            where_conditions=[WhereCondition(column="b", operator=">", value=1)],
            group_by=["a"],
            having="COUNT(*) > 0",
            order_by=[OrderByClause(column="a")],
            limit=3,
        )
        sql = Spider2Builder(spec).build()
        positions = {
            kw: sql.index(kw)
            for kw in ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"]
        }
        ordered = sorted(positions, key=lambda k: positions[k])
        assert ordered == ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"]
