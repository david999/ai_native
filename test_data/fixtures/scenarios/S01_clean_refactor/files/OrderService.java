package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public int calculateTotal(int quantity, int unitPrice) {
        return computeLineTotal(quantity, unitPrice);
    }

    private int computeLineTotal(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
