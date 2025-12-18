import 'dart:async';
import 'package:chinese_lunar_calendar/chinese_lunar_calendar.dart';
import 'package:flutter/material.dart';
import 'package:table_calendar/table_calendar.dart';
import 'package:zzcc/core/utils/color_utils.dart';

class CalendarWidget extends StatefulWidget {
  const CalendarWidget({super.key});

  @override
  State<CalendarWidget> createState() => _CalendarWidgetState();
}

class _CalendarWidgetState extends State<CalendarWidget> {
  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;
  ViewMode _currentView = ViewMode.month;
  int _currentYear = DateTime.now().year;
  String _currentTime = '';

  @override
  void initState() {
    super.initState();
    _updateCurrentTime();
    Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _updateCurrentTime();
        });
      }
    });
  }

  void _updateCurrentTime() {
    final now = DateTime.now();
    _currentTime = '${now.year}年${now.month}月${now.day}日 ${_formatTime(now.hour)}:${_formatTime(now.minute)}:${_formatTime(now.second)}';
  }

  String _formatTime(int value) {
    return value.toString().padLeft(2, '0');
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.calendar_today, size: 30),
                          SizedBox(width: 10),
                          Text('日历', style: TextStyle(fontSize: 18)),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        _currentTime,
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.grey.shade600,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
                _buildViewToggle(),
              ],
            ),
            const SizedBox(height: 20),
            Expanded(child: _buildCurrentView()),
          ],
        ),
      ),
    );
  }

  bool _isDateInRange(DateTime date) {
    final minDate = DateTime(1900, 1, 1);
    final maxDate = DateTime(2100, 12, 31);
    return date.isAfter(minDate) && date.isBefore(maxDate);
  }

  void _showJumpToDateDialog() {
    final yearController = TextEditingController();
    final monthController = TextEditingController();
    final dayController = TextEditingController();
    bool isLunarCalendar = false;

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('日期跳转'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: yearController,
                      decoration: const InputDecoration(labelText: '年'),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: monthController,
                      decoration: const InputDecoration(labelText: '月'),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: dayController,
                      decoration: const InputDecoration(labelText: '日'),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Checkbox(
                    value: isLunarCalendar,
                    onChanged: (value) {
                      setDialogState(() {
                        isLunarCalendar = value ?? false;
                      });
                    },
                  ),
                  const Text('农历日期'),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () {
                final year = int.tryParse(yearController.text);
                final month = int.tryParse(monthController.text);
                final day = int.tryParse(dayController.text);
                
                if (year != null && month != null && day != null && 
                    month >= 1 && month <= 12 && day >= 1 && day <= 31) {
                  
                  DateTime targetDate;
                  if (isLunarCalendar) {
                    // 精确的农历跳转逻辑
                    targetDate = _findLunarDate(year, month, day);
                    
                    if (targetDate.isAfter(DateTime.utc(1900, 1, 1))) {  // 修改为1900年
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('已跳转到农历$year年$month月$day日'),
                          duration: const Duration(seconds: 2),
                        ),
                      );
                    } else {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('未找到对应的农历日期')),
                      );
                      return;
                    }
                  } else {
                    // 公历跳转
                    targetDate = DateTime(year, month, day);
                  }
                  
                  // 检查日期是否在有效范围内，修改为1900-2100年
                  final minDate = DateTime.utc(1900, 1, 1);
                  final maxDate = DateTime.utc(2100, 12, 31);
                  
                  if (targetDate.isAfter(minDate) && targetDate.isBefore(maxDate)) {
                    setState(() {
                      _focusedDay = targetDate;
                      _selectedDay = targetDate;
                      _currentView = ViewMode.month;
                    });
                    Navigator.pop(context);
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('日期超出范围 (1900-2100)')),  // 修改提示信息
                    );
                  }
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('请输入有效的日期')),
                  );
                }
              },
              child: const Text('跳转'),
            ),
          ],
        ),
      ),
    );
  }

  DateTime _findLunarDate(int targetLunarYear, int targetLunarMonth, int targetLunarDay) {
    // 1. 在目标农历年前后各搜索一年范围
    int startYear = (targetLunarYear - 1).clamp(1900, 2100);
    int endYear = (targetLunarYear + 1).clamp(1900, 2100);
    DateTime startDate = DateTime(startYear, 1, 1);
    DateTime endDate = DateTime(endYear, 12, 31);
    
    // 2. 遍历搜索范围内的每一天
    DateTime currentDate = startDate;
    while (currentDate.isBefore(endDate)) {
      try {
        // 获取当前日期的农历信息
        final lunarCalendar = LunarCalendar.from(
          utcDateTime: currentDate.toUtc(),
        );
        
        // 提取农历日期信息
        final lunarYear = lunarCalendar.lunarDate.lunarYear;
        final lunarMonth = lunarCalendar.lunarDate.lunarMonth.number;
        final lunarDay = lunarCalendar.lunarDate.lunarDay;
        final isLeapMonth = lunarCalendar.lunarDate.lunarMonth.isLeapMonth;
        
        // 使用 toString() 方法获取年份字符串，然后转换为整数
        final lunarYearString = lunarYear.toString();
        final lunarYearInt = int.tryParse(lunarYearString) ?? 0;
        
        // 检查是否匹配目标农历日期
        bool isMatch = lunarYearInt == targetLunarYear && 
                      lunarDay == targetLunarDay;
        
        // 月份匹配逻辑
        if (isMatch) {
          // 普通月份匹配
          if (lunarMonth == targetLunarMonth && !isLeapMonth) {
            return currentDate;
          }
          
          // 闰月匹配：如果目标月份等于当前月份且是闰月
          // 或者目标月份等于当前月份+1（因为闰月会重复月份数字）
          if (isLeapMonth) {
            if (lunarMonth == targetLunarMonth || 
                (lunarMonth == targetLunarMonth - 1 && targetLunarMonth > 1)) {
              return currentDate;
            }
          }
        }
      } catch (e) {
        // 忽略转换错误，继续搜索
      }
      
      // 移动到下一天
      currentDate = currentDate.add(const Duration(days: 1));
    }
    
    // 如果没找到，尝试使用近似算法
    return _findApproximateLunarDate(targetLunarYear, targetLunarMonth, targetLunarDay);
  }

  DateTime _findApproximateLunarDate(int targetLunarYear, int targetLunarMonth, int targetLunarDay) {
    // 近似算法：农历日期 ≈ 公历日期 + 固定偏移量
    // 计算春节日期作为基准
    DateTime springFestival = _findSpringFestival(targetLunarYear);
    
    // 计算目标农历日期相对于春节的偏移量
    // 假设每月30天，这是一个粗略的近似
    int approximateOffset = (targetLunarMonth - 1) * 30 + (targetLunarDay - 1);
    
    return springFestival.add(Duration(days: approximateOffset));
  }

  DateTime _findSpringFestival(int lunarYear) {
    // 春节通常在1月21日至2月20日之间
    // 这里使用一个简单的查找方法
    DateTime startDate = DateTime(lunarYear, 1, 21);
    DateTime endDate = DateTime(lunarYear, 2, 20);
    
    DateTime currentDate = startDate;
    while (currentDate.isBefore(endDate)) {
      try {
        final lunarCalendar = LunarCalendar.from(utcDateTime: currentDate.toUtc());
        final lunarMonth = lunarCalendar.lunarDate.lunarMonth.number;
        final lunarDay = lunarCalendar.lunarDate.lunarDay;
        
        // 春节是农历正月初一
        if (lunarMonth == 1 && lunarDay == 1) {
          return currentDate;
        }
      } catch (e) {
        // 忽略错误
      }
      
      currentDate = currentDate.add(const Duration(days: 1));
    }
    
    // 如果没找到，返回一个默认的春节日期（2月1日）
    return DateTime(lunarYear, 2, 1);
  }

  // 在 _buildViewToggle() 方法返回的 Row 中添加跳转按钮
  Widget _buildViewToggle() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.grey.shade100,
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildViewButton('年', ViewMode.year),
              const SizedBox(width: 8),
              _buildViewButton('月', ViewMode.month),
              const SizedBox(width: 8),
              _buildViewButton('周', ViewMode.week),
              const SizedBox(width: 8),
              _buildViewButton('日', ViewMode.day),
            ],
          ),
        ),
        const SizedBox(width: 8),
        IconButton(
          icon: const Icon(Icons.calendar_today, size: 20),
          onPressed: _showJumpToDateDialog,
          tooltip: '日期跳转',
        ),
      ],
    );
  }

  Widget _buildViewButton(String text, ViewMode mode) {
    final isSelected = _currentView == mode;
    return GestureDetector(
      onTap: () {
        setState(() {
          _currentView = mode;
          _selectedDay = null;
        });
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? Theme.of(context).primaryColor : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Text(
          text,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.grey.shade700,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }

  Widget _buildCurrentView() {
    switch (_currentView) {
      case ViewMode.year:
        return _buildYearView();
      case ViewMode.month:
        return _buildMonthView();
      case ViewMode.week:
        return _buildWeekView();
      case ViewMode.day:
        return _buildDayView();
    }
  }

  Widget _buildYearView() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: () {
                  if (_currentYear > 1900) {
                    setState(() {
                      _currentYear--;
                    });
                  }
                },
              ),
              Text(
                '$_currentYear年',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: () {
                  if (_currentYear < 2100) {
                    setState(() {
                      _currentYear++;
                    });
                  }
                },
              ),
              const Spacer(),
              TextButton(
                onPressed: () {
                  setState(() {
                    _currentYear = DateTime.now().year;
                  });
                },
                child: const Text('今天'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Expanded(
          child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 4,
              crossAxisSpacing: 8,
              mainAxisSpacing: 8,
            ),
            itemCount: 12,
            itemBuilder: (context, index) {
              final month = index + 1;
              return Card(
                child: InkWell(
                  onTap: () {
                    setState(() {
                      _currentView = ViewMode.month;
                      _focusedDay = DateTime(_currentYear, month);
                    });
                  },
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '$month月',
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _getMonthEventsCount(_currentYear, month).toString(),
                          style: TextStyle(
                            color: Theme.of(context).primaryColor,
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const Text('事件', style: TextStyle(fontSize: 10)),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildMonthView() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: () {
                  final previousMonth = DateTime(_focusedDay.year, _focusedDay.month - 1);
                  if (_isDateInRange(previousMonth)) {
                    setState(() {
                      _focusedDay = previousMonth;
                    });
                  }
                },
              ),
              Text(
                '${_focusedDay.year}年${_focusedDay.month}月',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: () {
                  final nextMonth = DateTime(_focusedDay.year, _focusedDay.month + 1);
                  if (_isDateInRange(nextMonth)) {
                    setState(() {
                      _focusedDay = nextMonth;
                    });
                  }
                },
              ),
              const Spacer(),
              TextButton(
                onPressed: () {
                  setState(() {
                    _focusedDay = DateTime.now();
                    _selectedDay = null;
                  });
                },
                child: const Text('今天'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Expanded(
          child: TableCalendar(
            firstDay: DateTime.utc(1900, 1, 1),
            lastDay: DateTime.utc(2100, 12, 31),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
            onDaySelected: (selectedDay, focusedDay) {
              setState(() {
                _selectedDay = selectedDay;
                _focusedDay = focusedDay;
              });
            },
            onPageChanged: (focusedDay) {
              setState(() {
                _focusedDay = focusedDay;
              });
            },
            calendarFormat: CalendarFormat.month,
            headerStyle: HeaderStyle(
              formatButtonVisible: false,
              titleCentered: false,
              headerPadding: EdgeInsets.zero,
              leftChevronVisible: false,
              rightChevronVisible: false,
              titleTextStyle: const TextStyle(fontSize: 0),
            ),
            calendarStyle: CalendarStyle(
              todayDecoration: BoxDecoration(
                color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.3),
                shape: BoxShape.circle,
              ),
              selectedDecoration: BoxDecoration(
                color: Theme.of(context).primaryColor,
                shape: BoxShape.circle,
              ),
              weekendTextStyle: TextStyle(color: Colors.red.shade400),
            ),
            daysOfWeekStyle: DaysOfWeekStyle(
              // 使用 dowTextFormatter 替代 dowLabelFormatter
              dowTextFormatter: (date, locale) {
                switch (date.weekday) {
                  case 1: return '周一';
                  case 2: return '周二';
                  case 3: return '周三';
                  case 4: return '周四';
                  case 5: return '周五';
                  case 6: return '周六';
                  case 7: return '周日';
                  default: return '';
                }
              },
              weekendStyle: TextStyle(color: Colors.red.shade400),
            ),
            calendarBuilders: CalendarBuilders(
              defaultBuilder: (context, day, focusedDay) {
                return _buildCalendarDay(day);
              },
              todayBuilder: (context, day, focusedDay) {
                return _buildCalendarDay(day, isToday: true);
              },
              selectedBuilder: (context, day, focusedDay) {
                return _buildCalendarDay(day, isSelected: true);
              },
              outsideBuilder: (context, day, focusedDay) {
                return _buildCalendarDay(day, isOutside: true);
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCalendarDay(DateTime day, {bool isToday = false, bool isSelected = false, bool isOutside = false}) {
    final lunarDate = _getLunarDate(day);
    final solarTerm = _getSolarTermName(day);
    
    final textColor = isOutside 
      ? Colors.grey.shade400 
      : (isSelected ? Colors.white : (isToday ? Theme.of(context).primaryColor : Colors.black));
    
    // 获取节气颜色
    final solarTermColor = _getSolarTermColor(solarTerm);
    
    // 判断是否是今天或选中状态，应用不同的样式
    final bool isSpecialState = isToday || isSelected;
    
    return Container(
      margin: const EdgeInsets.all(1),
      padding: isSpecialState 
        ? const EdgeInsets.all(8) // 今天或选中状态增加内边距
        : const EdgeInsets.symmetric(vertical: 2),
      constraints: isSpecialState
        ? const BoxConstraints(maxHeight: 55, minHeight: 45) // 今天或选中状态增加高度
        : const BoxConstraints(maxHeight: 45, minHeight: 35),
      decoration: isSelected
          ? BoxDecoration(
              color: Theme.of(context).primaryColor,
              shape: BoxShape.circle,
              // 添加阴影效果，使选中状态更明显
              boxShadow: [
                BoxShadow(
                  color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.5),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
              ],
            )
          : (isToday
              ? BoxDecoration(
                  color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.3),
                  shape: BoxShape.circle,
                  // 为今天状态也添加轻微的阴影效果
                  boxShadow: [
                    BoxShadow(
                      color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.2),
                      blurRadius: 2,
                      offset: const Offset(0, 1),
                    ),
                  ],
                )
              : null),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // 公历日期
          Text(
            day.day.toString(),
            style: TextStyle(
              fontSize: isSpecialState ? 16 : 14, // 今天或选中状态字体稍大
              fontWeight: isToday ? FontWeight.bold : FontWeight.normal,
              color: textColor,
              height: 1.0,
            ),
          ),
          const SizedBox(height: 1),
          // 农历日期和节气显示在同一行
          RichText(
            text: TextSpan(
              children: [
                // 农历日期
                TextSpan(
                  text: lunarDate,
                  style: TextStyle(
                    fontSize: isSpecialState ? 10 : 9, // 今天或选中状态字体稍大
                    color: textColor,
                    height: 1.0,
                  ),
                ),
                // 如果有节气，追加在后面
                if (solarTerm.isNotEmpty)
                  TextSpan(
                    text: ' $solarTerm',
                    style: TextStyle(
                      fontSize: isSpecialState ? 10 : 9, // 今天或选中状态字体稍大
                      color: solarTermColor,
                      fontWeight: FontWeight.bold,
                      height: 1.0,
                    ),
                  ),
              ],
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  Color _getSolarTermColor(String solarTerm) {
    // 将繁体节气名称转换为简体
    String simplifiedTerm = _convertTraditionalToSimplified(solarTerm);
    
    // 根据简体节气名称返回不同颜色
    switch (simplifiedTerm) {
      case '立春':
      case '雨水':
      case '惊蛰':
      case '春分':
      case '清明':
      case '谷雨':
        return Colors.green; // 春季节气用绿色
      
      case '立夏':
      case '小满':
      case '芒种':
      case '夏至':
      case '小暑':
      case '大暑':
        return Colors.red; // 夏季节气用红色
      
      case '立秋':
      case '处暑':
      case '白露':
      case '秋分':
      case '寒露':
      case '霜降':
        return Colors.orange; // 秋季节气用橙色
      
      case '立冬':
      case '小雪':
      case '大雪':
      case '冬至':
      case '小寒':
      case '大寒':
        return Colors.blue; // 冬季节气用蓝色
      
      default:
        return Colors.purple; // 其他节气用紫色
    }
  }

  String _convertTraditionalToSimplified(String term) {
    // 创建繁体到简体的映射表
    final Map<String, String> traditionalToSimplified = {
      '驚蟄': '惊蛰',
      '穀雨': '谷雨',
      '小滿': '小满',
      '芒種': '芒种',
      '處暑': '处暑',
      '白露': '白露', // 保持不变
      '秋分': '秋分', // 保持不变
      '寒露': '寒露', // 保持不变
      '霜降': '霜降', // 保持不变
      '立冬': '立冬', // 保持不变
      '小雪': '小雪', // 保持不变
      '大雪': '大雪', // 保持不变
      '冬至': '冬至', // 保持不变
      '小寒': '小寒', // 保持不变
      '大寒': '大寒', // 保持不变
      '立春': '立春', // 保持不变
      '雨水': '雨水', // 保持不变
      '春分': '春分', // 保持不变
      '清明': '清明', // 保持不变
      '立夏': '立夏', // 保持不变
      '夏至': '夏至', // 保持不变
      '小暑': '小暑', // 保持不变
      '大暑': '大暑', // 保持不变
      '立秋': '立秋', // 保持不变
    };
    
    // 如果映射表中存在繁体，返回简体；否则返回原词
    return traditionalToSimplified[term] ?? term;
  }

  String _getLunarDate(DateTime day) {
    try {
      // 使用示例中的方法获取农历日期
      final lunarCalendar = LunarCalendar.from(
        utcDateTime: day.toUtc(),
      );
      
      // 获取农历日期的数字表示
      final lunarDay = lunarCalendar.lunarDate.lunarDay;
      
      // 获取农历月份的数字表示
      final lunarMonth = lunarCalendar.lunarDate.lunarMonth.number;
      
      // 获取是否是闰月
      final isLeapMonth = lunarCalendar.lunarDate.lunarMonth.isLeapMonth;
      
      // 如果是初一，显示月份和日子（如"正月初一"）
      if (lunarDay == 1) {
        // 获取月份的中文名称
        final monthName = _getLunarMonthName(lunarMonth, isLeapMonth);
        return '$monthName初一';
      } 
      // 如果不是初一，只显示日子（如"初二"）
      else {
        return _getLunarDayName(lunarDay);
      }
    } catch (e) {
      // 如果库调用失败，返回备用显示
      return '??';
    }
  }

  // 辅助方法：将农历月份的数字转换为中文名称
  String _getLunarMonthName(int month, bool isLeapMonth) {
    if (month < 1 || month > 12) return '??';
    
    final monthNames = {
      1: '正月', 2: '二月', 3: '三月', 4: '四月', 5: '五月', 6: '六月',
      7: '七月', 8: '八月', 9: '九月', 10: '十月', 11: '冬月', 12: '腊月'
    };
    
    String monthName = monthNames[month] ?? '??';
    
    // 如果是闰月，添加"闰"前缀
    if (isLeapMonth) {
      monthName = '闰$monthName';
    }
    
    return monthName;
  }

  // 辅助方法：将农历日期的数字转换为中文名称
  String _getLunarDayName(int day) {
    if (day < 1 || day > 30) return '??';
    
    final dayNames = {
      1: '初一', 2: '初二', 3: '初三', 4: '初四', 5: '初五',
      6: '初六', 7: '初七', 8: '初八', 9: '初九', 10: '初十',
      11: '十一', 12: '十二', 13: '十三', 14: '十四', 15: '十五',
      16: '十六', 17: '十七', 18: '十八', 19: '十九', 20: '二十',
      21: '廿一', 22: '廿二', 23: '廿三', 24: '廿四', 25: '廿五',
      26: '廿六', 27: '廿七', 28: '廿八', 29: '廿九', 30: '三十'
    };
    
    return dayNames[day] ?? '??';
  }

  String _getSolarTermName(DateTime day) {
    try {
      final lunarCalendar = LunarCalendar.from(
        utcDateTime: day.toUtc(),
      );
      
      final solarTerm = lunarCalendar.localTime.getSolarTerm();
      if (solarTerm != null) {
        // 从 SolarTerm 对象中提取节气名称
        final termString = solarTerm.toString();
        
        // 使用正则表达式提取节气名称
        final match = RegExp(r'Located\(([^,]+)').firstMatch(termString);
        if (match != null && match.groupCount >= 1) {
          String extractedTerm = match.group(1)!;
          // 将提取的节气名称转换为简体
          return _convertTraditionalToSimplified(extractedTerm);
        }
        
        // 如果上面的方法不工作，尝试其他提取方式
        if (termString.contains('name:')) {
          final nameMatch = RegExp(r'name:\s*([^,]+)').firstMatch(termString);
          if (nameMatch != null && nameMatch.groupCount >= 1) {
            String extractedTerm = nameMatch.group(1)!.trim();
            // 将提取的节气名称转换为简体
            return _convertTraditionalToSimplified(extractedTerm);
          }
        }
        
        // 如果还是无法提取，返回空字符串
        return '';
      }
      return '';
    } catch (e) {
      return '';
    }
  }

  bool isSameMonth(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month;
  }

  Widget _buildWeekView() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: () {
                  final previousWeek = _focusedDay.subtract(const Duration(days: 7));
                  if (_isDateInRange(previousWeek)) {
                    setState(() {
                      _focusedDay = previousWeek;
                    });
                  }
                },
              ),
              Text(
                '${_focusedDay.year}年${_focusedDay.month}月 第${_getWeekNumber(_focusedDay)}周',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: () {
                  final nextWeek = _focusedDay.add(const Duration(days: 7));
                  if (_isDateInRange(nextWeek)) {
                    setState(() {
                      _focusedDay = nextWeek;
                    });
                  }
                },
              ),
              const Spacer(),
              TextButton(
                onPressed: () {
                  setState(() {
                    _focusedDay = DateTime.now();
                    _selectedDay = null;
                  });
                },
                child: const Text('今天'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Expanded(
          child: TableCalendar(
            firstDay: DateTime.utc(1900, 1, 1),
            lastDay: DateTime.utc(2100, 12, 31),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
            onDaySelected: (selectedDay, focusedDay) {
              setState(() {
                _selectedDay = selectedDay;
                _focusedDay = focusedDay;
              });
            },
            onPageChanged: (focusedDay) {
              setState(() {
                _focusedDay = focusedDay;
              });
            },
            calendarFormat: CalendarFormat.week,
            headerStyle: HeaderStyle(
              formatButtonVisible: false,
              titleCentered: false,
              headerPadding: EdgeInsets.zero,
              leftChevronVisible: false,
              rightChevronVisible: false,
              titleTextStyle: const TextStyle(fontSize: 0),
            ),
            calendarStyle: CalendarStyle(
              todayDecoration: BoxDecoration(
                color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.3),
                shape: BoxShape.circle,
              ),
              selectedDecoration: BoxDecoration(
                color: Theme.of(context).primaryColor,
                shape: BoxShape.circle,
              ),
              // 使用 outsideTextStyle 替代 outsideStyle
              outsideTextStyle: TextStyle(color: Colors.grey.shade400),
              weekendTextStyle: TextStyle(color: Colors.red.shade400),
            ),
            daysOfWeekStyle: DaysOfWeekStyle(
              // 使用 dowTextFormatter 替代 dowLabelFormatter
              dowTextFormatter: (date, locale) {
                switch (date.weekday) {
                  case 1: return '周一';
                  case 2: return '周二';
                  case 3: return '周三';
                  case 4: return '周四';
                  case 5: return '周五';
                  case 6: return '周六';
                  case 7: return '周日';
                  default: return '';
                }
              },
              weekendStyle: TextStyle(color: Colors.red.shade400),
            ),
            calendarBuilders: CalendarBuilders(
              defaultBuilder: (context, day, focusedDay) {
                // 判断日期是否在当前月
                final isOutside = !isSameMonth(day, focusedDay);
                return _buildCalendarDay(day, isOutside: isOutside);
              },
              todayBuilder: (context, day, focusedDay) {
                // 判断日期是否在当前月
                final isOutside = !isSameMonth(day, focusedDay);
                return _buildCalendarDay(day, isToday: true, isOutside: isOutside);
              },
              selectedBuilder: (context, day, focusedDay) {
                // 判断日期是否在当前月
                final isOutside = !isSameMonth(day, focusedDay);
                return _buildCalendarDay(day, isSelected: true, isOutside: isOutside);
              },
              // 添加外部日期构建器
              outsideBuilder: (context, day, focusedDay) {
                return _buildCalendarDay(day, isOutside: true);
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDayView() {
    final displayDay = _selectedDay ?? DateTime.now();
    
    final events = _getEventsForDay(displayDay);
    
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: () {
                  final previousDay = displayDay.subtract(const Duration(days: 1));
                  if (_isDateInRange(previousDay)) {
                    setState(() {
                      _selectedDay = previousDay;
                    });
                  }
                },
              ),
              Column(
                children: [
                  Text(
                    '${displayDay.year}年${displayDay.month}月${displayDay.day}日',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    _getLunarDate(displayDay),
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: () {
                  final nextDay = displayDay.add(const Duration(days: 1));
                  if (_isDateInRange(nextDay)) {
                    setState(() {
                      _selectedDay = nextDay;
                    });
                  }
                },
              ),
              const Spacer(),
              TextButton(
                onPressed: () {
                  setState(() {
                    _selectedDay = DateTime.now();
                  });
                },
                child: const Text('今天'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Expanded(
          child: events.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.event_note, size: 48, color: Colors.grey.shade400),
                      const SizedBox(height: 8),
                      Text(
                        '这天没有事件',
                        style: TextStyle(color: Colors.grey.shade600),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: events.length,
                  itemBuilder: (context, index) {
                    final event = events[index];
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: Container(
                          width: 8,
                          height: 40,
                          decoration: BoxDecoration(
                            color: Theme.of(context).primaryColor,
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                        title: Text(event.title),
                        subtitle: Text('${event.startTime} - ${event.endTime}'),
                        trailing: IconButton(
                          icon: const Icon(Icons.more_vert, size: 20),
                          onPressed: () {},
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  int _getWeekNumber(DateTime date) {
    final firstDayOfYear = DateTime(date.year, 1, 1);
    final daysDiff = date.difference(firstDayOfYear).inDays;
    return ((daysDiff + firstDayOfYear.weekday + 6) / 7).ceil();
  }

  int _getMonthEventsCount(int year, int month) {
    return (month % 3) + 2;
  }

  List<CalendarEvent> _getEventsForDay(DateTime day) {
    if (day.day % 3 == 0) {
      return [
        CalendarEvent(
          title: '团队会议',
          startTime: '09:00',
          endTime: '10:30',
          date: day,
        ),
        CalendarEvent(
          title: '客户拜访',
          startTime: '14:00',
          endTime: '16:00',
          date: day,
        ),
      ];
    } else if (day.day % 5 == 0) {
      return [
        CalendarEvent(
          title: '项目评审',
          startTime: '10:00',
          endTime: '12:00',
          date: day,
        ),
      ];
    }
    return [];
  }
}

enum ViewMode {
  year,
  month,
  week,
  day,
}

class CalendarEvent {
  final String title;
  final String startTime;
  final String endTime;
  final DateTime date;

  CalendarEvent({
    required this.title,
    required this.startTime,
    required this.endTime,
    required this.date,
  });
}