"""快速排序的两种实现。

- quick_sort:        函数式写法，返回新列表，不修改入参（易读，适合教学）
- quick_sort_inplace: 原地写法（Lomuto 分区），修改入参，空间开销更小
"""

from typing import List


def quick_sort(arr: List[int]) -> List[int]:
    """返回 arr 的升序副本（不修改原列表）。"""
    if len(arr) <= 1:
        return list(arr)
    pivot = arr[len(arr) // 2]
    less = [x for x in arr if x < pivot]
    equal = [x for x in arr if x == pivot]
    greater = [x for x in arr if x > pivot]
    return quick_sort(less) + equal + quick_sort(greater)


def quick_sort_inplace(arr: List[int], low: int = 0, high: int = -1) -> None:
    """原地升序排序 arr（Lomuto 分区方案）。"""
    if high == -1:
        high = len(arr) - 1
    if low >= high:
        return
    pivot_index = _partition(arr, low, high)
    quick_sort_inplace(arr, low, pivot_index - 1)
    quick_sort_inplace(arr, pivot_index + 1, high)


def _partition(arr: List[int], low: int, high: int) -> int:
    """以 arr[high] 为基准分区，返回基准最终下标。"""
    pivot = arr[high]
    i = low - 1  # i 指向「小于 pivot 区间」的最后一个位置
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1


if __name__ == "__main__":
    cases = [
        [],
        [1],
        [2, 1],
        [5, 3, 8, 1, 9, 2, 7],
        [3, 3, 3, 1, 1],
        [-4, 10, 0, -4, 7],
    ]

    for data in cases:
        expected = sorted(data)

        assert quick_sort(data) == expected
        assert data == list(data), "quick_sort 不应修改入参"

        buf = list(data)
        quick_sort_inplace(buf)
        assert buf == expected

        print(f"{data}  ->  {expected}")

    print("全部用例通过")
