-- Fix employee.department to match actual Department.department_name
-- 08-22: directory tree 显示5/5员工归位
UPDATE employees SET department='研发一部' WHERE employee_name='张三';
UPDATE employees SET department='销售部' WHERE employee_name='李四';
UPDATE employees SET department='行政部' WHERE employee_name='赵六';
UPDATE employees SET department='运营部' WHERE employee_name='孙七';
